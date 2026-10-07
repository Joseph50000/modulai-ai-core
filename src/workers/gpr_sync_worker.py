import sys
import os
import logging

# Ajouter la racine du projet ai-core-fastapi au sys.path
sys.path.append(os.path.join(os.path.dirname(__file__), "..", ".."))

from src.sync import SyncService, SyncJobRequest, DocumentTemplateConfig, SyncScheduler, ScheduledJobSpec

logger = logging.getLogger(__name__)

# Données d'exemple fournies par le module
GPR_SAMPLE_RECORDS = [
    {
        "id": 1,
        "objet_categorie": "Facturation",
        "motif_reclamation": "Double débit",
        "texte_plainte": "J'ai été débité deux fois de la même facture.",
        "statut_final": "Résolu",
        "texte_solution": "Remboursement du trop perçu effectué."
    },
    {
        "id": 2,
        "objet_categorie": "Technique",
        "motif_reclamation": "Panne",
        "texte_plainte": "Ma box internet redémarre en boucle depuis hier soir.",
        "statut_final": "Résolu",
        "texte_solution": "Remplacement du matériel planifié."
    }
]


def build_gpr_sync_request() -> SyncJobRequest:
    """Construit une requête d'ingestion déclarative paramétrée pour le module."""
    return SyncJobRequest(
        collection_name="gpr_claims",
        connector_type="json",
        connector_config={"records": GPR_SAMPLE_RECORDS},
        template_config=DocumentTemplateConfig(
            template="Plainte ({objet_categorie} - {motif_reclamation}): {texte_plainte} \nSolution apportée: {texte_solution}",
            id_field="id",
            id_prefix="gpr_claim_",
            metadata_fields=["objet_categorie", "motif_reclamation", "statut_final"],
            source_name="gpr_module"
        ),
        batch_size=50,
        clear_existing=False
    )


def perform_gpr_sync():
    """Tâche de synchronisation exécutée via le moteur générique SyncService."""
    logger.info("Début de la synchronisation via SyncService...")
    service = SyncService()
    request = build_gpr_sync_request()
    response = service.execute_job(request)
    logger.info(f"Synchronisation terminée: statut={response.status}, total_indexé={response.total_indexed}")
    return response


def start_scheduler():
    """Démarre la planification avec le planificateur SyncScheduler générique."""
    scheduler = SyncScheduler()
    spec = ScheduledJobSpec(
        job_id="gpr_daily_sync",
        interval_seconds=86400,
        cron_expression="0 2 * * *",
        sync_request=build_gpr_sync_request()
    )
    scheduler.add_sync_job(spec)
    logger.info("Worker GPR: Tâche planifiée enregistrée dans SyncScheduler.")
    return scheduler


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    perform_gpr_sync()
