import unittest
import os
import re
import tempfile
import json
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient

from main import app
from src.sync.schemas import (
    ConnectorType,
    RestConnectorConfig,
    JsonConnectorConfig,
    DocumentTemplateConfig,
    SyncJobRequest,
    SyncJobResponse,
    ScheduledJobSpec
)
from src.sync.connectors import get_connector, RestConnector, JsonArrayConnector
from src.sync.transformer import DocumentTransformer
from src.sync.service import SyncService
from src.sync.scheduler import SyncScheduler


class MockVectorStore:
    """Mock léger de VectorStore pour tester les insertions de façon hermétique."""
    def __init__(self, collection_name: str = "test_col"):
        self.collection_name = collection_name
        self.indexed_docs = []
        self.indexed_metadatas = []
        self.indexed_ids = []
        self.cleared = False

    def upsert_documents(self, documents, metadatas, ids):
        self.indexed_docs.extend(documents)
        self.indexed_metadatas.extend(metadatas)
        self.indexed_ids.extend(ids)

    def clear(self):
        self.cleared = True
        self.indexed_docs = []
        self.indexed_metadatas = []
        self.indexed_ids = []

    def count(self):
        return len(self.indexed_docs)


class TestSyncEngine(unittest.TestCase):

    def setUp(self):
        self.client = TestClient(app)

    # 1. Validation des Schémas Pydantic
    def test_sync_schemas_validation(self):
        tmpl = DocumentTemplateConfig(
            template="Événement : {title} - {desc}",
            id_field="id",
            id_prefix="evt_",
            metadata_fields=["category", "severity"]
        )
        self.assertEqual(tmpl.id_prefix, "evt_")
        self.assertEqual(tmpl.metadata_fields, ["category", "severity"])

        req = SyncJobRequest(
            collection_name="it_incidents",
            connector_type="json",
            connector_config={"records": [{"id": 1, "title": "Erreur serveur"}]},
            template_config=tmpl,
            batch_size=50,
            clear_existing=True
        )
        self.assertEqual(req.collection_name, "it_incidents")
        self.assertTrue(req.clear_existing)

        spec = ScheduledJobSpec(
            job_id="job_cron_1",
            cron_expression="0 * * * *",
            interval_seconds=3600,
            sync_request=req
        )
        self.assertEqual(spec.job_id, "job_cron_1")
        self.assertEqual(spec.interval_seconds, 3600)

    # 2. Transformateur de Documents : Interpolation & IDs
    def test_document_transformer_interpolation(self):
        tmpl = DocumentTemplateConfig(
            template="Ticket #{ticket_num} : {title} [{priority}]\nDescription: {details}\nRésolution: {fix}",
            id_field="ticket_num",
            id_prefix="tkt_",
            metadata_fields=["priority", "department"],
            source_name="jira_sync"
        )
        transformer = DocumentTransformer(tmpl)

        records = [
            {
                "ticket_num": "IT-101",
                "title": "Panne réseau",
                "priority": "HIGH",
                "details": "Switch baie B hors service",
                "fix": "Remplacement du câble d'alimentation",
                "department": "Infrastructure"
            },
            {
                "ticket_num": "IT-102",
                "title": "Accès VPN",
                "priority": "LOW",
                # 'details' et 'fix' manquants volontairement
                "department": "Support"
            }
        ]

        docs = transformer.transform_all(records)
        self.assertEqual(len(docs), 2)

        doc1 = docs[0]
        self.assertEqual(doc1["id"], "tkt_IT-101")
        self.assertIn("Ticket #IT-101 : Panne réseau [HIGH]", doc1["text"])
        self.assertIn("Résolution: Remplacement du câble d'alimentation", doc1["text"])
        self.assertEqual(doc1["metadata"]["priority"], "HIGH")
        self.assertEqual(doc1["metadata"]["department"], "Infrastructure")
        self.assertEqual(doc1["metadata"]["source"], "jira_sync")

        doc2 = docs[1]
        self.assertEqual(doc2["id"], "tkt_IT-102")
        self.assertIn("Ticket #IT-102 : Accès VPN [LOW]", doc2["text"])
        self.assertEqual(doc2["metadata"]["priority"], "LOW")

    # 3. Transformateur : Fallback Hash SHA-256 sans id_field
    def test_document_transformer_sha_fallback(self):
        tmpl = DocumentTemplateConfig(
            template="Note: {content}",
            id_field=None,
            id_prefix="note_",
            metadata_fields=[]
        )
        transformer = DocumentTransformer(tmpl)
        docs = transformer.transform_all([{"content": "Procédure de redémarrage"}])
        self.assertEqual(len(docs), 1)
        self.assertTrue(docs[0]["id"].startswith("note_"))
        self.assertGreater(len(docs[0]["id"]), 8)

    # 4. Connecteur JSON (Mémoire & Fichier)
    def test_json_connector(self):
        # Mémoire
        records_in = [{"col1": "A", "val": 10}, {"col1": "B", "val": 20}]
        conn_mem = JsonArrayConnector(records=records_in)
        self.assertEqual(len(conn_mem.fetch_records()), 2)

        # Fichier JSON temporaire
        with tempfile.NamedTemporaryFile("w+", suffix=".json", delete=False, encoding="utf-8") as f:
            json.dump([{"item": "X"}, {"item": "Y"}], f)
            temp_path = f.name

        try:
            conn_file = JsonArrayConnector(file_path=temp_path)
            res = conn_file.fetch_records()
            self.assertEqual(len(res), 2)
            self.assertEqual(res[0]["item"], "X")
        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)

    # 5. Connecteur REST avec Mock HTTP
    @patch("requests.get")
    def test_rest_connector_with_items_path(self, mock_get):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "status": "success",
            "data": {
                "results": [
                    {"code": "PRD-1", "nom": "Clavier USB", "prix": 29.99},
                    {"code": "PRD-2", "nom": "Souris Sans Fil", "prix": 19.99}
                ]
            }
        }
        mock_get.return_value = mock_response

        conn = RestConnector(
            url="https://api.shop.com/v1/products",
            items_path="data.results",
            headers={"Authorization": "Bearer token123"}
        )
        records = conn.fetch_records()
        self.assertEqual(len(records), 2)
        self.assertEqual(records[0]["code"], "PRD-1")
        self.assertEqual(records[1]["nom"], "Souris Sans Fil")

    # 6. Service de Synchronisation (Pipeline complet et batching)
    def test_sync_service_pipeline(self):
        mock_store = MockVectorStore(collection_name="products_catalog")
        service = SyncService(vector_store_getter=lambda col: mock_store)

        records = [
            {"sku": f"SKU-{i}", "label": f"Article {i}", "category": "Bureau", "price": i * 10}
            for i in range(1, 11)
        ]

        req = SyncJobRequest(
            collection_name="products_catalog",
            connector_type="json",
            connector_config={"records": records},
            template_config=DocumentTemplateConfig(
                template="Produit {sku} : {label} ({category}) au tarif de {price}€",
                id_field="sku",
                id_prefix="p_",
                metadata_fields=["category", "price"]
            ),
            batch_size=4,  # Testera plusieurs lots
            clear_existing=True
        )

        response = service.execute_job(req)
        self.assertEqual(response.status, "success")
        self.assertEqual(response.total_fetched, 10)
        self.assertEqual(response.total_indexed, 10)
        self.assertTrue(mock_store.cleared)
        self.assertEqual(len(mock_store.indexed_docs), 10)
        self.assertEqual(mock_store.indexed_ids[0], "p_SKU-1")
        self.assertIn("au tarif de 10€", mock_store.indexed_docs[0])

    # 7. Planificateur SyncScheduler
    def test_sync_scheduler_operations(self):
        mock_store = MockVectorStore()
        service = SyncService(vector_store_getter=lambda col: mock_store)
        scheduler = SyncScheduler(sync_service=service)

        spec = ScheduledJobSpec(
            job_id="test_scheduled_job",
            interval_seconds=3600,
            sync_request=SyncJobRequest(
                collection_name="temp_col",
                connector_type="json",
                connector_config={"records": [{"id": 1, "text": "Test"}]},
                template_config=DocumentTemplateConfig(template="Doc: {text}", id_field="id")
            )
        )

        # Ajout
        sched_res = scheduler.add_sync_job(spec)
        self.assertEqual(sched_res["job_id"], "test_scheduled_job")
        self.assertEqual(sched_res["status"], "scheduled")

        # Liste
        jobs = scheduler.list_jobs()
        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0]["job_id"], "test_scheduled_job")

        # Déclenchement manuel
        trigger_res = scheduler.trigger_job("test_scheduled_job")
        self.assertEqual(trigger_res.status, "success")
        self.assertEqual(trigger_res.total_indexed, 1)

        # Suppression
        removed = scheduler.remove_sync_job("test_scheduled_job")
        self.assertTrue(removed)
        self.assertEqual(len(scheduler.list_jobs()), 0)

        # Arrêt
        scheduler.shutdown()

    # 8. Endpoints HTTP FastAPI
    def test_fastapi_sync_endpoints(self):
        mock_http_store = MockVectorStore("http_test_collection")
        with patch("main.sync_service.vector_store_getter", return_value=mock_http_store):
            payload = {
                "collection_name": "http_test_collection",
                "connector_type": "json",
                "connector_config": {
                    "records": [
                        {"id": "doc1", "title": "Guide onboarding", "content": "Bienvenue dans l'équipe"},
                        {"id": "doc2", "title": "Politique sécurité", "content": "Mots de passe sécurisés"}
                    ]
                },
                "template_config": {
                    "template": "{title} : {content}",
                    "id_field": "id",
                    "id_prefix": "doc_",
                    "metadata_fields": ["title"]
                },
                "batch_size": 10,
                "clear_existing": False
            }

            # POST /api/sync/execute
            resp = self.client.post("/api/sync/execute", json=payload)
            self.assertEqual(resp.status_code, 200)
            data = resp.json()
            self.assertEqual(data["status"], "success")
            self.assertEqual(data["total_fetched"], 2)
            self.assertEqual(data["total_indexed"], 2)

        # POST /api/sync/schedule
        schedule_payload = {
            "job_id": "fastapi_cron_test",
            "interval_seconds": 7200,
            "sync_request": payload
        }
        sched_resp = self.client.post("/api/sync/schedule", json=schedule_payload)
        self.assertEqual(sched_resp.status_code, 200)
        self.assertEqual(sched_resp.json()["job_id"], "fastapi_cron_test")

        # GET /api/sync/jobs
        jobs_resp = self.client.get("/api/sync/jobs")
        self.assertEqual(jobs_resp.status_code, 200)
        jobs_list = jobs_resp.json().get("jobs", [])
        self.assertTrue(any(j["job_id"] == "fastapi_cron_test" for j in jobs_list))

        # DELETE /api/sync/jobs/{job_id}
        del_resp = self.client.delete("/api/sync/jobs/fastapi_cron_test")
        self.assertEqual(del_resp.status_code, 200)

    # 9. Test Multi-Domaines (Agnosticisme absolu)
    def test_multi_domain_agnosticism(self):
        mock_store = MockVectorStore()
        service = SyncService(vector_store_getter=lambda col: mock_store)

        # Domaine 1 : Support IT
        it_req = SyncJobRequest(
            collection_name="it_knowledge",
            connector_type="json",
            connector_config={
                "records": [
                    {"err_code": "ERR-504", "system": "Gateway", "resolution": "Augmenter timeout proxy"}
                ]
            },
            template_config=DocumentTemplateConfig(
                template="Erreur {err_code} sur {system}. Procédure : {resolution}",
                id_field="err_code",
                id_prefix="it_",
                metadata_fields=["system"]
            )
        )
        res_it = service.execute_job(it_req)
        self.assertEqual(res_it.status, "success")
        self.assertEqual(res_it.total_indexed, 1)

        # Domaine 2 : Ressources Humaines
        rh_req = SyncJobRequest(
            collection_name="rh_jobs",
            connector_type="json",
            connector_config={
                "records": [
                    {"job_title": "Ingénieur DevOps", "level": "Senior", "skills": "Docker, Kubernetes, CI/CD"}
                ]
            },
            template_config=DocumentTemplateConfig(
                template="Poste : {job_title} ({level})\nCompétences requises : {skills}",
                id_field="job_title",
                id_prefix="job_",
                metadata_fields=["level"]
            )
        )
        res_rh = service.execute_job(rh_req)
        self.assertEqual(res_rh.status, "success")
        self.assertEqual(res_rh.total_indexed, 1)

    # 10. Audit de pureté : Zéro code bancaire en dur dans src/sync/
    def test_zero_banking_hardcoded_in_src_sync(self):
        sync_dir = os.path.join(os.path.dirname(__file__), "..", "src", "sync")
        forbidden_pattern = re.compile(r"(?i)\b(bceao|dab|agio|reclamation|plainte|gpr_claim)\b")

        violations = []
        for root, _, files in os.walk(sync_dir):
            for file in files:
                if file.endswith(".py"):
                    file_path = os.path.join(root, file)
                    with open(file_path, "r", encoding="utf-8") as f:
                        for line_no, line in enumerate(f, 1):
                            match = forbidden_pattern.search(line)
                            if match:
                                violations.append(f"{file}:{line_no}: '{match.group(0)}' trouvé dans '{line.strip()}'")

        self.assertEqual(
            violations,
            [],
            f"Des termes spécifiques au domaine bancaire ont été trouvés en dur dans src/sync/ : {violations}"
        )


if __name__ == "__main__":
    unittest.main()
