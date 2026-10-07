import threading
import time
import datetime
import logging
from typing import Dict, Any, List, Optional
from src.sync.schemas import ScheduledJobSpec, SyncJobResponse
from src.sync.service import SyncService

logger = logging.getLogger(__name__)


def _utcnow_iso() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def _dump_model(model_obj: Any) -> Dict[str, Any]:
    if hasattr(model_obj, "model_dump"):
        return model_obj.model_dump()
    elif hasattr(model_obj, "dict"):
        return model_obj.dict()
    return dict(model_obj)


class SyncScheduler:
    """Gestionnaire autonome de planification de tâches de synchronisation périodiques."""

    def __init__(self, sync_service: Optional[SyncService] = None):
        self.sync_service = sync_service or SyncService()
        self.jobs: Dict[str, Dict[str, Any]] = {}
        self._lock = threading.Lock()
        self._timers: Dict[str, threading.Timer] = {}
        self._running = True

    def _execute_and_reschedule(self, job_id: str):
        """Exécute un job planifié puis programme sa prochaine exécution."""
        with self._lock:
            if not self._running or job_id not in self.jobs:
                return
            job_info = self.jobs[job_id]

        spec: ScheduledJobSpec = job_info["spec"]
        logger.info(f"[SyncScheduler] Exécution programmée du job '{job_id}'...")

        try:
            response: SyncJobResponse = self.sync_service.execute_job(spec.sync_request)
            with self._lock:
                if job_id in self.jobs:
                    self.jobs[job_id]["last_run"] = _utcnow_iso()
                    self.jobs[job_id]["last_status"] = response.status
                    self.jobs[job_id]["last_result"] = _dump_model(response)
        except Exception as e:
            logger.error(f"[SyncScheduler] Erreur lors de l'exécution du job '{job_id}': {e}")
            with self._lock:
                if job_id in self.jobs:
                    self.jobs[job_id]["last_run"] = _utcnow_iso()
                    self.jobs[job_id]["last_status"] = "error"
                    self.jobs[job_id]["last_result"] = {"error": str(e)}

        # Re-planification pour la prochaine échéance si interval_seconds > 0
        with self._lock:
            if self._running and job_id in self.jobs:
                interval = spec.interval_seconds or 3600
                timer = threading.Timer(interval, self._execute_and_reschedule, args=[job_id])
                timer.daemon = True
                self._timers[job_id] = timer
                timer.start()
                self.jobs[job_id]["next_run"] = (
                    datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(seconds=interval)
                ).isoformat()

    def add_sync_job(self, spec: ScheduledJobSpec) -> Dict[str, Any]:
        """Ajoute ou remplace un job planifié."""
        with self._lock:
            job_id = spec.job_id

            # Arrêter l'ancien timer si existant
            if job_id in self._timers:
                self._timers[job_id].cancel()
                del self._timers[job_id]

            interval = spec.interval_seconds
            # Conversion minimale si cron_expression est fournie sans interval_seconds
            if not interval and spec.cron_expression:
                interval = 3600  # Défaut 1 heure pour une expression cron générale

            interval = max(1, interval or 3600)

            next_run = (datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(seconds=interval)).isoformat()

            self.jobs[job_id] = {
                "job_id": job_id,
                "spec": spec,
                "created_at": _utcnow_iso(),
                "interval_seconds": interval,
                "cron_expression": spec.cron_expression,
                "next_run": next_run,
                "last_run": None,
                "last_status": "pending"
            }

            timer = threading.Timer(interval, self._execute_and_reschedule, args=[job_id])
            timer.daemon = True
            self._timers[job_id] = timer
            timer.start()

            return {
                "job_id": job_id,
                "status": "scheduled",
                "next_run": next_run,
                "interval_seconds": interval
            }

    def remove_sync_job(self, job_id: str) -> bool:
        """Supprime un job planifié et annule son timer."""
        with self._lock:
            if job_id in self._timers:
                self._timers[job_id].cancel()
                del self._timers[job_id]
            if job_id in self.jobs:
                del self.jobs[job_id]
                return True
            return False

    def trigger_job(self, job_id: str) -> SyncJobResponse:
        """Déclenche immédiatement l'exécution manuelle d'un job planifié."""
        with self._lock:
            if job_id not in self.jobs:
                raise ValueError(f"Job inconnu : '{job_id}'")
            spec: ScheduledJobSpec = self.jobs[job_id]["spec"]

        response = self.sync_service.execute_job(spec.sync_request)
        with self._lock:
            if job_id in self.jobs:
                self.jobs[job_id]["last_run"] = _utcnow_iso()
                self.jobs[job_id]["last_status"] = response.status
                self.jobs[job_id]["last_result"] = _dump_model(response)
        return response

    def list_jobs(self) -> List[Dict[str, Any]]:
        """Renvoie la liste des jobs enregistrés et leurs métriques."""
        with self._lock:
            result = []
            for j_id, j_data in self.jobs.items():
                result.append({
                    "job_id": j_id,
                    "collection_name": j_data["spec"].sync_request.collection_name,
                    "interval_seconds": j_data.get("interval_seconds"),
                    "cron_expression": j_data.get("cron_expression"),
                    "created_at": j_data.get("created_at"),
                    "next_run": j_data.get("next_run"),
                    "last_run": j_data.get("last_run"),
                    "last_status": j_data.get("last_status")
                })
            return result

    def shutdown(self):
        """Arrête tous les timers en cours proprement."""
        with self._lock:
            self._running = False
            for timer in self._timers.values():
                timer.cancel()
            self._timers.clear()
