import os
import re
import glob
import json
import unittest
from unittest.mock import MagicMock, patch

from src.nlp.schemas import NLPAnalyzeRequest, NLPAnalyzeResponse
from src.nlp.sensitive_words_detector import SensitiveWordsDetector
from src.nlp.sentiment_analyzer import SentimentAnalyzer
from src.nlp.summary_generator import SummaryGenerator
from src.nlp.hierarchical_classifier import HierarchicalClassifier
from src.nlp.urgency_evaluator import UrgencyEvaluator
from src.nlp.service import NLPService

class TestNLPEngine(unittest.TestCase):

    def setUp(self):
        self.mock_llm = MagicMock()

    # 1. Test Détecteur de Mots Sensibles
    def test_sensitive_words_detector(self):
        detector = SensitiveWordsDetector()
        
        # Test sans mots-clés
        self.assertEqual(detector.detect("Un texte sans danger", []), [])
        self.assertEqual(detector.detect("Un texte sans danger", None), [])

        # Test avec liste dynamique et flexions (accents, pluriels, casse)
        keywords = ["fraude", "tribunal", "urgent", "perte", "menace"]
        text = "C'est une FRAUDE évidente, nous avons subi de lourdes pertes et nous irons devant les tribunaux ou c'est URGENT !"
        
        detected = detector.detect(text, keywords)
        self.assertIn("fraude", detected)
        self.assertIn("perte", detected)
        self.assertIn("tribunal", detected)
        self.assertIn("urgent", detected)
        self.assertNotIn("menace", detected)

    # 2. Test Analyse de Sentiment
    def test_sentiment_analyzer(self):
        analyzer = SentimentAnalyzer()

        # Positif
        res_pos, score_pos = analyzer.analyze("Un service excellent, très rapide et un accueil parfait, merci !")
        self.assertEqual(res_pos, "positif")
        self.assertGreater(score_pos, 0.15)

        # Neutre
        res_neu, score_neu = analyzer.analyze("Le dossier a été déposé le 12 octobre à l'accueil.")
        self.assertEqual(res_neu, "neutre")

        # Négatif / Très négatif
        res_neg, score_neg = analyzer.analyze("C'est une honte absolue, inadmissible, un scandale total !!")
        self.assertEqual(res_neg, "tres_negatif")
        self.assertLess(score_neg, -0.3)

        # Négation ("pas bon")
        res_pas_bon, score_pas_bon = analyzer.analyze("Ce service n'est pas bon du tout.")
        self.assertIn(res_pas_bon, ["negatif", "tres_negatif", "neutre"])
        self.assertNotEqual(res_pas_bon, "positif")

    # 3. Test Générateur de Résumé
    def test_summary_generator(self):
        generator = SummaryGenerator()
        text = "Première phrase introductive de la situation. Deuxième phrase avec des détails secondaires. Troisième phrase de conclusion importante."
        
        summary = generator.generate_extractive(text, max_words=20)
        self.assertIn("Première phrase introductive", summary)
        self.assertIn("conclusion importante", summary)

    # 4. Test Évaluateur d'Urgence (Heuristique & Configurable)
    def test_urgency_evaluator_heuristics_and_custom_scale(self):
        evaluator = UrgencyEvaluator(llm_provider=None)

        # Échelle standard française
        urgency, reason = evaluator.evaluate(
            text="Alerte critique immédiate !",
            urgency_levels=["MINEUR", "MOYEN", "GRAVE"],
            sensitive_keywords_detected=["fraude"],
            sentiment="tres_negatif"
        )
        self.assertEqual(urgency, "GRAVE")

        # Échelle personnalisée anglophone
        custom_levels = ["LOW", "MEDIUM", "HIGH", "CRITICAL"]
        urgency_custom, _ = evaluator.evaluate(
            text="Short alert",
            urgency_levels=custom_levels,
            sensitive_keywords_detected=["ransomware"],
            sentiment="tres_negatif"
        )
        self.assertEqual(urgency_custom, "CRITICAL")

    # 5. Test Classifieur Hiérarchique avec Mock LLM
    def test_hierarchical_classifier_mock(self):
        self.mock_llm.generate.return_value = json.dumps({
            "category": "INFORMATIQUE",
            "subcategory": "PANNE_RESEAU",
            "analyse_du_probleme": "Le routeur de l'agence ne répond plus suite à une coupure."
        })

        classifier = HierarchicalClassifier(llm_provider=self.mock_llm)
        taxonomy = {
            "INFORMATIQUE": {
                "description": "Problèmes de matériel et infrastructure",
                "subcategories": [
                    {"label": "PANNE_RESEAU", "description": "Coupure switch/routeur", "severity": "HIGH"}
                ]
            }
        }

        cat, sub, reason = classifier.classify(
            text="Le switch principal ne fonctionne plus du tout.",
            taxonomy=taxonomy,
            context_nature="INCIDENT_IT"
        )

        self.assertEqual(cat, "INFORMATIQUE")
        self.assertEqual(sub, "PANNE_RESEAU")
        self.assertIn("routeur", reason)

    # 6. Test NLP Service Complet (End-to-End)
    def test_nlp_service_pipeline(self):
        self.mock_llm.generate.return_value = json.dumps({
            "category": "LOGISTIQUE",
            "subcategory": "RETARD_LIVRAISON",
            "analyse_du_probleme": "Le colis n'a pas été livré dans les délais annoncés.",
            "urgence": "MOYEN"
        })

        service = NLPService(llm_provider=self.mock_llm)
        
        req = NLPAnalyzeRequest(
            text="Mon colis en retard expédié il y a dix jours n'est toujours pas arrivé, c'est inacceptable.",
            taxonomy={
                "LOGISTIQUE": {
                    "subcategories": [
                        {"label": "RETARD_LIVRAISON", "severity": "MOYEN"}
                    ]
                }
            },
            sensitive_keywords=["retard", "perte", "inadmissible"],
            urgency_levels=["MINEUR", "MOYEN", "GRAVE"],
            context_nature="COMMANDE"
        )

        response = service.process(req)

        self.assertEqual(response.status, "success")
        self.assertEqual(response.suggested_category, "LOGISTIQUE")
        self.assertEqual(response.suggested_subcategory, "RETARD_LIVRAISON")
        self.assertIn("retard", response.sensitive_keywords_detected)
        self.assertIsNotNone(response.summary)
        self.assertGreater(response.execution_time_ms, -1)

    # 7. Test Streaming Generator (SSE Events)
    def test_nlp_service_stream(self):
        self.mock_llm.generate.return_value = json.dumps({
            "category": "SUPPORT",
            "subcategory": "ACCES",
            "analyse_du_probleme": "Mot de passe oublié.",
            "urgence": "MINEUR"
        })

        service = NLPService(llm_provider=self.mock_llm)
        req = NLPAnalyzeRequest(
            text="Impossible de me connecter à mon compte ce matin.",
            taxonomy={"SUPPORT": {"subcategories": [{"label": "ACCES"}]}},
            sensitive_keywords=["bloque"],
            urgency_levels=["MINEUR", "MOYEN", "GRAVE"]
        )

        events = list(service.process_stream(req))
        event_types = [e.get("type") for e in events]

        self.assertIn("correlation", event_types)
        self.assertIn("init_base", event_types)
        self.assertIn("init_urgence", event_types)
        self.assertIn("final", event_types)

    # 8. Test Multi-Domaines (Validation de l'Agnosticisme sans code dur)
    def test_multi_domain_agnosticism(self):
        # Domaine 1 : Ressources Humaines
        rh_taxonomy = {
            "CONTRAT": {"subcategories": [{"label": "RUPTURE", "severity": "HIGH"}]},
            "CONDITIONS": {"subcategories": [{"label": "HARCELEMENT", "severity": "CRITICAL"}]}
        }
        rh_detector = SensitiveWordsDetector()
        detected_rh = rh_detector.detect(
            "Je signale une situation de harcelement moral grave de la part de mon responsable.",
            ["harcelement", "prud'hommes", "demission"]
        )
        self.assertIn("harcelement", detected_rh)

        # Domaine 2 : Santé / Médical
        sante_taxonomy = {
            "URGENCE_VITALE": {"subcategories": [{"label": "CARDIO", "severity": "CRITICAL"}]},
            "CONSULTATION": {"subcategories": [{"label": "ROUTINE", "severity": "LOW"}]}
        }
        sante_detector = SensitiveWordsDetector()
        detected_sante = sante_detector.detect(
            "Patient présentant une douleur thoracique aiguë et un malaise.",
            ["arret", "thoracique", "malaise", "coma"]
        )
        self.assertIn("thoracique", detected_sante)
        self.assertIn("malaise", detected_sante)

    # 9. Audit Strict Zéro Code Dur dans le Core (src/nlp)
    def test_zero_banking_hardcoded_in_src_nlp(self):
        nlp_dir = os.path.join(os.path.dirname(__file__), "..", "src", "nlp")
        py_files = glob.glob(os.path.join(nlp_dir, "*.py"))

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

    # 10. Test FastAPI HTTP Endpoints
    def test_fastapi_http_endpoints(self):
        from fastapi.testclient import TestClient
        from main import app

        client = TestClient(app)

        payload = {
            "text": "Le logiciel plante systématiquement au démarrage depuis la mise à jour.",
            "sensitive_keywords": ["plante", "bloque"],
            "urgency_levels": ["MINEUR", "MOYEN", "GRAVE"],
            "taxonomy": {
                "TECHNIQUE": {
                    "subcategories": [
                        {"label": "BUG_LOGICIEL", "description": "Crash de l'application", "severity": "MOYEN"}
                    ]
                }
            },
            "enable_llm_reasoning": False
        }

        response = client.post("/api/nlp/analyze", json=payload)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["status"], "success")
        self.assertIn("plante", data["sensitive_keywords_detected"])
        self.assertIn("suggested_category", data)
        self.assertIn("correlation_id", data)

    # 11. Test FastAPI HTTP Streaming Endpoint (SSE)
    def test_fastapi_http_stream_endpoint(self):
        from fastapi.testclient import TestClient
        from main import app

        client = TestClient(app)
        payload = {
            "text": "Le système refuse mon mot de passe à chaque tentative.",
            "sensitive_keywords": ["refuse"],
            "enable_llm_reasoning": False
        }

        response = client.post("/api/nlp/analyze/stream", json=payload)
        self.assertEqual(response.status_code, 200)
        self.assertIn("text/event-stream", response.headers.get("content-type", ""))
        self.assertIn("init_base", response.text)
        self.assertIn("init_urgence", response.text)
        self.assertIn("final", response.text)

    # 12. Test Audit Traçabilité (Envoi vers Backend AIExecution)
    @patch("requests.post")
    def test_audit_logging_call(self, mock_post):
        from fastapi.testclient import TestClient
        from main import app

        client = TestClient(app)
        payload = {
            "text": "Incident critique détecté sur le serveur principal.",
            "project_id": "test-project-123",
            "module_key": "it-support",
            "use_case_key": "incident-triage",
            "enable_llm_reasoning": False
        }

        response = client.post("/api/nlp/analyze", json=payload)
        self.assertEqual(response.status_code, 200)

        # Vérifier que requests.post a bien été appelé vers /aiexecution avec le bon format
        self.assertTrue(mock_post.called)
        call_args, call_kwargs = mock_post.call_args
        self.assertIn("/aiexecution", call_args[0])
        audit_payload = call_kwargs.get("json", {})
        self.assertEqual(audit_payload.get("project_id"), "test-project-123")
        self.assertEqual(audit_payload.get("module_name"), "it-support")
        self.assertEqual(audit_payload.get("use_case"), "incident-triage")
        self.assertEqual(audit_payload.get("status"), "success")
        self.assertIn("urgency", audit_payload.get("output", ""))

if __name__ == "__main__":
    unittest.main()

