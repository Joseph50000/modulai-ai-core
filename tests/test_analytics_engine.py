import os
import re
import glob
import json
import unittest
from unittest.mock import MagicMock, patch

from src.analytics.schemas import (
    FieldDefinition,
    DatasetSchema,
    FilterClause,
    MetricSpec,
    AnalyticsIntent,
    AnalyticsQueryRequest,
    AnalyticsChartResponse,
)
from src.analytics.nl_to_intent import NLToIntentEngine
from src.analytics.data_engine import DataEngine
from src.analytics.echarts_builder import EChartsBuilder
from src.analytics.service import AnalyticsService

class TestAnalyticsEngine(unittest.TestCase):

    def setUp(self):
        self.mock_llm = MagicMock()
        # Schéma générique de test (ex: Gestion de Parc Informatique)
        self.sample_schema = DatasetSchema(
            fields=[
                FieldDefinition(name="serveur", type="string", label="Nom du serveur"),
                FieldDefinition(name="datacenter", type="string", label="Localisation"),
                FieldDefinition(name="statut", type="string", label="État de service"),
                FieldDefinition(name="charge_cpu", type="number", label="Charge CPU (%)"),
                FieldDefinition(name="memoire_go", type="number", label="Mémoire RAM (Go)"),
                FieldDefinition(name="date_mise_en_service", type="date", label="Date d'installation")
            ]
        )

        # Données de test
        self.sample_records = [
            {"serveur": "SRV-01", "datacenter": "Paris", "statut": "actif", "charge_cpu": 75.5, "memoire_go": 64},
            {"serveur": "SRV-02", "datacenter": "Paris", "statut": "actif", "charge_cpu": 45.0, "memoire_go": 32},
            {"serveur": "SRV-03", "datacenter": "Lyon", "statut": "maintenance", "charge_cpu": 10.0, "memoire_go": 16},
            {"serveur": "SRV-04", "datacenter": "Lyon", "statut": "actif", "charge_cpu": 88.0, "memoire_go": 128},
            {"serveur": "SRV-05", "datacenter": "Marseille", "statut": "actif", "charge_cpu": 60.0, "memoire_go": 64},
        ]

    # 1. Test Validation des Schémas Pydantic
    def test_analytics_schemas(self):
        field = FieldDefinition(name="category", type="string", label="Catégorie")
        schema = DatasetSchema(fields=[field], description="Catalogue")
        self.assertEqual(len(schema.fields), 1)
        self.assertEqual(schema.fields[0].name, "category")

        intent = AnalyticsIntent(
            chart_type="bar",
            group_by=["category"],
            metrics=[MetricSpec(field="sales", operation="sum", alias="total_sales", label="Ventes")],
            title="Ventes par Catégorie"
        )
        self.assertEqual(intent.chart_type, "bar")
        self.assertEqual(intent.metrics[0].operation, "sum")

    # 2. Test NLToIntentEngine (Inférence heuristique)
    def test_nl_to_intent_heuristic(self):
        engine = NLToIntentEngine()

        # Cas 1 : Question de répartition catégorielle -> Pie/Doughnut
        q1 = "Quelle est la repartition des serveurs par datacenter ?"
        intent1 = engine.infer_intent(q1, self.sample_schema)
        self.assertEqual(intent1.chart_type, "pie")
        self.assertIn("datacenter", intent1.group_by)
        self.assertEqual(intent1.metrics[0].operation, "count")

        # Cas 2 : Question d'évolution temporelle -> Line
        q2 = "Affiche l'evolution dans le temps de l'installation"
        intent2 = engine.infer_intent(q2, self.sample_schema)
        self.assertEqual(intent2.chart_type, "line")

        # Cas 3 : Question de moyenne numérique -> Bar + avg
        q3 = "Quelle est la charge cpu moyenne par datacenter ?"
        intent3 = engine.infer_intent(q3, self.sample_schema)
        self.assertEqual(intent3.chart_type, "bar")
        self.assertIn("datacenter", intent3.group_by)
        self.assertEqual(intent3.metrics[0].operation, "avg")
        self.assertEqual(intent3.metrics[0].field, "charge_cpu")

    # 3. Test NLToIntentEngine avec Mock LLM
    def test_nl_to_intent_llm(self):
        mock_output = json.dumps({
            "chart_type": "bar",
            "group_by": ["datacenter"],
            "metrics": [{"field": "charge_cpu", "operation": "max", "alias": "max_cpu", "label": "CPU Max"}],
            "filters": [{"field": "statut", "operator": "eq", "value": "actif"}],
            "sort_by": "max_cpu",
            "sort_order": "desc",
            "limit": 5,
            "title": "Pic de charge CPU par Datacenter"
        })
        self.mock_llm.generate.return_value = mock_output

        engine = NLToIntentEngine(llm_provider=self.mock_llm)
        intent = engine.infer_intent("Plafond CPU par datacenter pour les serveurs actifs", self.sample_schema)

        self.assertEqual(intent.chart_type, "bar")
        self.assertIn("datacenter", intent.group_by)
        self.assertEqual(intent.metrics[0].operation, "max")
        self.assertEqual(intent.filters[0].field, "statut")
        self.assertEqual(intent.filters[0].value, "actif")

    # 4. Test DataEngine (Filtrage & Agrégations)
    def test_data_engine_aggregation(self):
        engine = DataEngine()

        # Filtrage seul
        filtered = engine.filter_records(
            self.sample_records,
            [FilterClause(field="statut", operator="eq", value="actif")]
        )
        self.assertEqual(len(filtered), 4)

        # Agrégation (Moyenne CPU par Datacenter pour les actifs)
        intent = AnalyticsIntent(
            chart_type="bar",
            group_by=["datacenter"],
            metrics=[MetricSpec(field="charge_cpu", operation="avg", alias="avg_cpu", label="Moyenne CPU")],
            filters=[FilterClause(field="statut", operator="eq", value="actif")],
            sort_by="avg_cpu",
            sort_order="desc"
        )

        results = engine.aggregate(self.sample_records, intent)
        self.assertEqual(len(results), 3) # Paris, Lyon, Marseille

        # Lyon actif a 1 serveur à 88% -> 88.0
        # Paris actif a 2 serveurs (75.5 et 45.0) -> moyenne 60.25
        # Marseille actif a 1 serveur à 60% -> 60.0
        self.assertEqual(results[0]["datacenter"], "Lyon")
        self.assertEqual(results[0]["avg_cpu"], 88.0)
        self.assertEqual(results[1]["datacenter"], "Paris")
        self.assertEqual(results[1]["avg_cpu"], 60.25)

    # 5. Test EChartsBuilder (Graphique en barres et en courbes)
    def test_echarts_builder_cartesian(self):
        builder = EChartsBuilder()
        intent = AnalyticsIntent(
            chart_type="bar",
            group_by=["datacenter"],
            metrics=[MetricSpec(field="charge_cpu", operation="avg", alias="avg_cpu", label="Moyenne CPU")],
            title="Consommation par Site"
        )
        agg_data = [
            {"datacenter": "Paris", "avg_cpu": 60.25, "_group_label": "Paris"},
            {"datacenter": "Lyon", "avg_cpu": 88.0, "_group_label": "Lyon"}
        ]

        option = builder.build_option(agg_data, intent)
        self.assertEqual(option["title"]["text"], "Consommation par Site")
        self.assertIn("xAxis", option)
        self.assertIn("yAxis", option)
        self.assertEqual(len(option["series"]), 1)
        self.assertEqual(option["series"][0]["type"], "bar")
        self.assertEqual(option["series"][0]["data"], [60.25, 88.0])

        # Test Line Chart
        intent.chart_type = "line"
        option_line = builder.build_option(agg_data, intent)
        self.assertEqual(option_line["series"][0]["type"], "line")
        self.assertTrue(option_line["series"][0]["smooth"])

    # 6. Test EChartsBuilder (Graphique en camembert et KPI)
    def test_echarts_builder_pie_and_kpi(self):
        builder = EChartsBuilder()
        intent_pie = AnalyticsIntent(
            chart_type="pie",
            group_by=["statut"],
            metrics=[MetricSpec(operation="count", alias="nb_srv", label="Nombre")],
            title="Répartition des Statuts"
        )
        agg_data = [
            {"statut": "actif", "nb_srv": 4, "_group_label": "actif"},
            {"statut": "maintenance", "nb_srv": 1, "_group_label": "maintenance"}
        ]

        option_pie = builder.build_option(agg_data, intent_pie)
        self.assertNotIn("xAxis", option_pie)
        self.assertEqual(option_pie["series"][0]["type"], "pie")
        self.assertEqual(len(option_pie["series"][0]["data"]), 2)
        self.assertEqual(option_pie["series"][0]["data"][0]["name"], "actif")
        self.assertEqual(option_pie["series"][0]["data"][0]["value"], 4)

        # Test Doughnut
        intent_pie.chart_type = "doughnut"
        option_doughnut = builder.build_option(agg_data, intent_pie)
        self.assertEqual(option_doughnut["series"][0]["radius"], ["40%", "70%"])

        # Test KPI
        intent_kpi = AnalyticsIntent(
            chart_type="kpi",
            metrics=[MetricSpec(operation="count", alias="nb_srv", label="Total Serveurs")]
        )
        option_kpi = builder.build_option(agg_data, intent_kpi)
        self.assertIn("graphic", option_kpi)

    # 7. Test Pipeline Global AnalyticsService
    def test_analytics_service_process(self):
        service = AnalyticsService(llm_provider=None)
        req = AnalyticsQueryRequest(
            query="Combien de serveurs par statut ?",
            dataset_schema=self.sample_schema,
            records=self.sample_records
        )

        resp = service.process_query(req)
        self.assertEqual(resp.status, "success")
        self.assertIsNotNone(resp.intent)
        self.assertIn("actif", [r.get("statut") for r in resp.aggregated_data])
        self.assertIsNotNone(resp.summary_insight)
        self.assertIn("actif", resp.summary_insight)
        self.assertGreater(resp.execution_time_ms, -1)

    # 8. Test FastAPI HTTP Endpoints (TestClient)
    @patch("main.analytics_service.intent_engine.llm_provider", None)
    def test_fastapi_http_endpoints(self):
        from fastapi.testclient import TestClient
        from main import app

        client = TestClient(app)

        # 1. Validation query requise
        res_err = client.post("/api/analytics/chart", json={"query": ""})
        self.assertEqual(res_err.status_code, 400)

        # 2. Requête d'intention (/api/analytics/query)
        payload_query = {
            "query": "Répartition des serveurs par datacenter",
            "dataset_schema": self.sample_schema.model_dump()
        }
        res_intent = client.post("/api/analytics/query", json=payload_query)
        self.assertEqual(res_intent.status_code, 200)
        data_intent = res_intent.json()
        self.assertIn("chart_type", data_intent)
        self.assertIn("group_by", data_intent)

        # 3. Requête complète (/api/analytics/chart)
        payload_chart = {
            "query": "Moyenne de la mémoire vive par datacenter",
            "dataset_schema": self.sample_schema.model_dump(),
            "records": self.sample_records
        }
        res_chart = client.post("/api/analytics/chart", json=payload_chart)
        self.assertEqual(res_chart.status_code, 200)
        data_chart = res_chart.json()
        self.assertEqual(data_chart["status"], "success")
        self.assertIn("echarts_option", data_chart)
        self.assertIn("aggregated_data", data_chart)
        self.assertIn("summary_insight", data_chart)

    # 9. Test Audit Traçabilité (Envoi vers Backend AIExecution)
    @patch("main.analytics_service.intent_engine.llm_provider", None)
    @patch("requests.post")
    def test_audit_logging_call(self, mock_post):
        from fastapi.testclient import TestClient
        from main import app

        client = TestClient(app)
        payload = {
            "query": "Analyse de la charge CPU moyenne par statut",
            "dataset_schema": self.sample_schema.model_dump(),
            "records": self.sample_records,
            "project_id": "proj-analytics-01",
            "module_key": "infra-monitoring",
            "use_case_key": "cpu-dashboard"
        }

        response = client.post("/api/analytics/chart", json=payload)
        self.assertEqual(response.status_code, 200)

        self.assertTrue(mock_post.called)
        call_args, call_kwargs = mock_post.call_args
        self.assertIn("/aiexecution", call_args[0])
        audit_payload = call_kwargs.get("json", {})
        self.assertEqual(audit_payload.get("project_id"), "proj-analytics-01")
        self.assertEqual(audit_payload.get("module_name"), "infra-monitoring")
        self.assertEqual(audit_payload.get("use_case"), "cpu-dashboard")
        self.assertEqual(audit_payload.get("status"), "success")

    # 10. Test Multi-Domaines (Validation de l'Agnosticisme sans code dur)
    def test_multi_domain_agnosticism(self):
        engine = NLToIntentEngine()
        data_engine = DataEngine()

        # Domaine 1 : E-Commerce & Ventes
        ecom_schema = DatasetSchema(fields=[
            FieldDefinition(name="categorie_produit", type="string", label="Rayon"),
            FieldDefinition(name="chiffre_affaires", type="number", label="Chiffre d'Affaires")
        ])
        ecom_records = [
            {"categorie_produit": "Électronique", "chiffre_affaires": 12000},
            {"categorie_produit": "Textile", "chiffre_affaires": 8500},
            {"categorie_produit": "Électronique", "chiffre_affaires": 15000}
        ]
        intent_ecom = engine.infer_intent("Total du chiffre d'affaires par categorie de produit", ecom_schema)
        self.assertEqual(intent_ecom.metrics[0].operation, "sum")
        agg_ecom = data_engine.aggregate(ecom_records, intent_ecom)
        self.assertEqual(len(agg_ecom), 2)
        self.assertEqual(agg_ecom[0]["categorie_produit"], "Électronique")
        self.assertEqual(agg_ecom[0]["metric_value"], 27000.0)

        # Domaine 2 : Ressources Humaines
        rh_schema = DatasetSchema(fields=[
            FieldDefinition(name="departement", type="string", label="Service"),
            FieldDefinition(name="salaire_brut", type="number", label="Salaire Annuel Brut")
        ])
        rh_records = [
            {"departement": "R&D", "salaire_brut": 55000},
            {"departement": "Marketing", "salaire_brut": 48000},
            {"departement": "R&D", "salaire_brut": 65000}
        ]
        intent_rh = engine.infer_intent("Salaire brut moyen par departement", rh_schema)
        self.assertEqual(intent_rh.metrics[0].operation, "avg")
        agg_rh = data_engine.aggregate(rh_records, intent_rh)
        self.assertEqual(len(agg_rh), 2)
        self.assertEqual(agg_rh[0]["departement"], "R&D")
        self.assertEqual(agg_rh[0]["metric_value"], 60000.0)

    # 11. Audit Strict Zéro Code Dur dans le Core (src/analytics)
    def test_zero_banking_hardcoded_in_src_analytics(self):
        analytics_dir = os.path.join(os.path.dirname(__file__), "..", "src", "analytics")
        py_files = glob.glob(os.path.join(analytics_dir, "*.py"))

        forbidden_terms = ["bceao", "dab", "agio", "compte bancaire", "reclamation bancaire"]

        for file_path in py_files:
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read().lower()
                for term in forbidden_terms:
                    pattern = rf"\b{re.escape(term)}\b"
                    self.assertIsNone(
                        re.search(pattern, content),
                        f"VIOLATION D'AGNOSTICISME : Terme métier '{term}' détecté en dur dans {os.path.basename(file_path)}"
                    )

if __name__ == "__main__":
    unittest.main()
