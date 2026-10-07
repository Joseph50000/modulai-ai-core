import os
import re
import glob
import json
import unittest
from unittest.mock import MagicMock, patch

from src.rag.schemas import (
    SearchSourceItem,
    RAGSearchRequest,
    RAGSearchResponse,
    PropositionItem,
    RAGResolveRequest,
    RAGResolveResponse,
)
from src.rag.filter_builder import FilterBuilder
from src.rag.context_aggregator import ContextAggregator
from src.rag.resolution_engine import ResolutionEngine
from src.rag.service import RAGService

class TestRAGEngine(unittest.TestCase):

    def setUp(self):
        self.mock_llm = MagicMock()

    # 1. Test FilterBuilder (ChromaDB syntax conversion)
    def test_filter_builder(self):
        self.assertIsNone(FilterBuilder.build(None))
        self.assertIsNone(FilterBuilder.build({}))

        # Filtre scalaire simple
        f1 = FilterBuilder.build({"status": "RESOLVED"})
        self.assertEqual(f1, {"status": "RESOLVED"})

        # Filtre avec liste converti en $in
        f2 = FilterBuilder.build({"category": ["HARDWARE", "NETWORK"]})
        self.assertEqual(f2, {"category": {"$in": ["HARDWARE", "NETWORK"]}})

        # Filtres multiples convertis en $and
        f3 = FilterBuilder.build({"status": "RESOLVED", "priority": "HIGH"})
        self.assertIn("$and", f3)
        self.assertEqual(len(f3["$and"]), 2)

        # Filtre avec opérateur $or explicite
        f4 = FilterBuilder.build({"$or": [{"type": "BUG"}, {"type": "INCIDENT"}]})
        self.assertIn("$or", f4)
        self.assertEqual(len(f4["$or"]), 2)

    # 2. Test ContextAggregator
    def test_context_aggregator(self):
        aggregator = ContextAggregator()

        hist_items = [
            {
                "id": "h1",
                "document": "Panne de ventilateur sur serveur rack",
                "metadata": {"solution": "Remplacement du bloc ventilateur et redémarrage"},
                "similarity_score": 0.88
            }
        ]
        doc_items = [
            {
                "id": "d1",
                "document": "Procédure P-42 : couper l'alimentation avant toute manipulation interne.",
                "metadata": {"title": "Guide Maintenance Serveur"},
                "similarity_score": 0.75
            }
        ]

        hist_text = aggregator.format_historical_context(hist_items)
        self.assertIn("Panne de ventilateur", hist_text)
        self.assertIn("Remplacement du bloc", hist_text)

        doc_text = aggregator.format_documentary_context(doc_items)
        self.assertIn("Guide Maintenance Serveur", doc_text)
        self.assertIn("Procédure P-42", doc_text)

        comb_text = aggregator.format_combined_context(hist_items, doc_items)
        self.assertIn("HISTORIQUES SIMILAIRES", comb_text)
        self.assertIn("CADRE DE RÉFÉRENCE", comb_text)

        # Fallback si vide
        self.assertIn("Aucun", aggregator.format_historical_context([]))
        self.assertIn("Aucune", aggregator.format_documentary_context([]))

    # 3. Test ResolutionEngine (Parsing et génération synchrone)
    def test_resolution_engine_sync(self):
        sample_output = (
            "RAISONNEMENT : Le composant réseau principal subit une surchauffe récurrente.\n"
            "1. Vérifier la ventilation du rack | Les sondes thermiques indiquent 75°C.\n"
            "2. Remplacer le ventilateur défectueux | Pièce disponible en stock sous référence V-12.\n"
            "3. Basculer le trafic sur le switch secondaire | Pour assurer la continuité de service."
        )
        self.mock_llm.generate.return_value = sample_output

        engine = ResolutionEngine(llm_provider=self.mock_llm)
        reasoning, propositions, raw_message = engine.resolve(
            query="Le switch réseau s'éteint tout seul après 10 minutes d'activité.",
            historical_context="Cas passé : surchauffe switch.",
            documentary_context="Procédure thermique.",
            combined_context="Contexte combiné.",
            num_propositions=3
        )

        self.assertIsNotNone(reasoning)
        self.assertIn("surchauffe récurrente", reasoning)
        self.assertEqual(len(propositions), 3)
        self.assertEqual(propositions[0].index, 1)
        self.assertEqual(propositions[0].title, "Vérifier la ventilation du rack")
        self.assertEqual(propositions[0].details, "Les sondes thermiques indiquent 75°C.")
        self.assertEqual(propositions[1].index, 2)
        self.assertEqual(propositions[2].index, 3)

    # 4. Test ResolutionEngine (Streaming)
    def test_resolution_engine_stream(self):
        self.mock_llm.generate_stream.return_value = iter(["RAISONNEMENT : ", "Analyse. ", "\n1. Action | Commentaire."])

        engine = ResolutionEngine(llm_provider=self.mock_llm)
        chunks = list(engine.resolve_stream(
            query="Problème",
            historical_context="",
            documentary_context="",
            combined_context=""
        ))
        self.assertGreaterEqual(len(chunks), 2)
        self.assertIn("RAISONNEMENT : ", "".join(chunks))

    # 5. Test RAGService (Resolve complet avec sources)
    def test_rag_service_resolve(self):
        mock_store = MagicMock()
        mock_store.search.return_value = [
            {
                "id": "item-1",
                "document": "Ticket résolu : bug d'affichage dashboard",
                "metadata": {"solution": "Vider le cache du navigateur"},
                "distance": 0.25,
                "similarity_score": 0.8
            }
        ]

        self.mock_llm.generate.return_value = (
            "RAISONNEMENT : Problème de cache local côté client.\n"
            "1. Vider le cache du navigateur | Résout 90% des erreurs d'affichage similaires.\n"
            "2. Tester en navigation privée | Pour vérifier l'isolation des cookies.\n"
            "3. Redémarrer la session utilisateur | Si les données persistent."
        )

        service = RAGService(
            llm_provider=self.mock_llm,
            vector_store_factory=lambda _: mock_store
        )

        req = RAGResolveRequest(
            query="Le tableau de bord n'affiche plus les graphiques.",
            historical_collection="resolved_tickets",
            documentary_collection="kb_docs",
            top_k_history=2,
            top_k_docs=2,
            num_propositions=3
        )

        resp = service.resolve(req)

        self.assertEqual(resp.status, "success")
        self.assertIn("cache local", resp.reasoning)
        self.assertEqual(len(resp.propositions), 3)
        self.assertEqual(len(resp.historical_sources), 1)
        self.assertEqual(resp.historical_sources[0].similarity_score, 0.8)
        self.assertGreater(resp.execution_time_ms, -1)

    # 6. Test RAGService (Streaming SSE events)
    def test_rag_service_stream(self):
        mock_store = MagicMock()
        mock_store.search.return_value = [
            {"id": "doc1", "document": "Manuel technique", "metadata": {"solution": "Redémarrer"}, "distance": 0.1, "similarity_score": 0.9}
        ]

        self.mock_llm.generate_stream.return_value = iter(["RAISONNEMENT : OK\n1. Solution | Justification"])

        service = RAGService(
            llm_provider=self.mock_llm,
            vector_store_factory=lambda _: mock_store
        )

        req = RAGResolveRequest(
            query="Erreur système",
            historical_collection="col_hist"
        )

        events = list(service.resolve_stream(req))
        types = [e.get("type") for e in events]

        self.assertIn("correlation", types)
        self.assertIn("sources", types)
        self.assertIn("chunk", types)
        self.assertIn("final", types)

    # 7. Test Orchestrator Multi-Context
    @patch("src.orchestrator.OllamaProvider.generate")
    @patch("requests.post")
    def test_orchestrator_multi_context(self, mock_post, mock_llm_gen):
        mock_llm_gen.return_value = "Réponse test générée avec succès"
        from src.orchestrator import Orchestrator

        orchestrator = Orchestrator()
        
        # Simuler un store avec des données de test
        mock_store = MagicMock()
        mock_store.search.return_value = [
            {"id": "1", "document": "Exemple passé résolu", "similarity_score": 0.85}
        ]
        orchestrator.get_vector_store = MagicMock(return_value=mock_store)

        payload = {
            "module": "it-support",
            "use_case": "troubleshooting",
            "user_prompt": "Mon imprimante ne répond plus",
            "system_prompt_template": "Rôle assistant.\nDoc: {{documentary_context}}\nHist: {{historical_context}}\nGlobal: {{context}}",
            "rag_config": {
                "enabled": True,
                "historical_collection": "it_past_tickets",
                "documentary_collection": "it_manuals",
                "top_k": 2
            }
        }

        # Mock de la résolution de configuration (évite l'appel HTTP vers Node Gateway)
        orchestrator.config_resolver.resolve = MagicMock(return_value={
            "snapshot": {
                "policy_violations": [],
                "rag": payload["rag_config"]
            },
            "prompt": {
                "instructions": payload["system_prompt_template"]
            }
        })

        result = orchestrator.execute(payload)
        self.assertEqual(result.get("status"), "success")
        self.assertTrue(mock_llm_gen.called)
        call_kwargs = mock_llm_gen.call_args[1]
        system_prompt = call_kwargs.get("system_prompt", "")
        self.assertIn("Exemple passé résolu", system_prompt)

    # 8. Test HTTP FastAPI Endpoints (TestClient)
    @patch("main.rag_service.resolution_engine.llm_provider.generate")
    @patch("main.rag_service.resolution_engine.llm_provider.generate_stream")
    def test_fastapi_http_resolve_endpoints(self, mock_stream, mock_generate):
        mock_generate.return_value = "RAISONNEMENT : Diagnostic OK\n1. Vérifier le scanner | Câble débranché"
        mock_stream.return_value = iter(["RAISONNEMENT : Diagnostic OK\n1. Vérifier le scanner | Câble débranché"])

        from fastapi.testclient import TestClient
        from main import app

        client = TestClient(app)

        # 1. Validation query requise
        res_err = client.post("/api/rag/resolve", json={"query": ""})
        self.assertEqual(res_err.status_code, 400)

        # 2. Résolution nominale
        payload = {
            "query": "Le scanner réseau refuse la connexion de l'utilisateur.",
            "num_propositions": 3
        }
        res_ok = client.post("/api/rag/resolve", json=payload)
        self.assertEqual(res_ok.status_code, 200)
        data = res_ok.json()
        self.assertEqual(data["status"], "success")
        self.assertIn("propositions", data)
        self.assertIn("correlation_id", data)

        # 3. Résolution streaming SSE
        res_stream = client.post("/api/rag/resolve/stream", json=payload)
        self.assertEqual(res_stream.status_code, 200)
        self.assertIn("text/event-stream", res_stream.headers.get("content-type", ""))
        self.assertIn("sources", res_stream.text)

    # 9. Test Audit Traçabilité (Envoi vers Backend AIExecution)
    @patch("main.rag_service.resolution_engine.llm_provider.generate")
    @patch("requests.post")
    def test_audit_logging_call(self, mock_post, mock_generate):
        mock_generate.return_value = "RAISONNEMENT : Audit nominal\n1. Action préventive | Justification"

        from fastapi.testclient import TestClient
        from main import app

        client = TestClient(app)
        payload = {
            "query": "Test audit traçabilité résolution RAG",
            "project_id": "proj-rag-123",
            "module_key": "maintenance",
            "use_case_key": "diagnostic-resolv"
        }

        response = client.post("/api/rag/resolve", json=payload)
        self.assertEqual(response.status_code, 200)

        self.assertTrue(mock_post.called)
        call_args, call_kwargs = mock_post.call_args
        self.assertIn("/aiexecution", call_args[0])
        audit_payload = call_kwargs.get("json", {})
        self.assertEqual(audit_payload.get("project_id"), "proj-rag-123")
        self.assertEqual(audit_payload.get("module_name"), "maintenance")
        self.assertEqual(audit_payload.get("use_case"), "diagnostic-resolv")
        self.assertEqual(audit_payload.get("status"), "success")

    # 10. Test Multi-Domaines (Validation de l'Agnosticisme sans code dur)
    def test_multi_domain_agnosticism(self):
        aggregator = ContextAggregator()
        engine = ResolutionEngine(llm_provider=self.mock_llm)

        # Domaine 1 : Maintenance Industrielle (Aéronautique / Usine)
        maint_query = "Vibration anormale sur le compresseur C-200"
        maint_prompt_sys, maint_prompt_usr = engine.build_prompts(
            query=maint_query,
            historical_context="- Cas passé : Remplacement roulement compresseur",
            documentary_context="- Manuel constructeur : seuil de vibration maxi 4.5 mm/s",
            combined_context="Contexte usine",
            num_propositions=3,
            system_role_instruction="Tu es un ingénieur expert en maintenance prédictive industrielle."
        )
        self.assertIn("maintenance prédictive", maint_prompt_sys)
        self.assertIn("compresseur", maint_prompt_usr)

        # Domaine 2 : Ressources Humaines
        rh_query = "Demande d'aménagement de temps partiel thérapeutique"
        rh_prompt_sys, rh_prompt_usr = engine.build_prompts(
            query=rh_query,
            historical_context="- Cas passé : Accord mi-temps 3 mois avec avis médecin travail",
            documentary_context="- Accord d'entreprise RH article 14",
            combined_context="Contexte RH",
            num_propositions=2,
            system_role_instruction="Tu es un conseiller juridique expert en droit du travail et gestion RH."
        )
        self.assertIn("droit du travail", rh_prompt_sys)
        self.assertIn("thérapeutique", rh_prompt_usr)

    # 11. Audit Strict Zéro Code Dur dans le Core (src/rag)
    def test_zero_banking_hardcoded_in_src_rag(self):
        rag_dir = os.path.join(os.path.dirname(__file__), "..", "src", "rag")
        py_files = glob.glob(os.path.join(rag_dir, "*.py"))

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
