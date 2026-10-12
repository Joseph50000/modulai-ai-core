import json
import unittest
from unittest.mock import MagicMock, patch

from src.audio.schemas import TranscribeRequest
from src.audio.service import AudioTranscriptionService
from src.audio.transcription_provider import TranscriptionProvider
from src.orchestrator import Orchestrator
from src.rag.vector_store import GenericVectorStore


class DummyLlmProvider:
    def __init__(self, response_text: str = '{"sentiment": "positif", "urgence": "MINEUR"}'):
        self.response_text = response_text
        self.last_system_prompt = None
        self.last_user_prompt = None
        self.last_options = None

    def generate(self, system_prompt: str, user_prompt: str, options: dict = None) -> str:
        self.last_system_prompt = system_prompt
        self.last_user_prompt = user_prompt
        self.last_options = options
        return self.response_text


class TestModularPillars(unittest.TestCase):
    """
    Tests unitaires validant l'autonomie et la composabilité des 3 Piliers Core de ModulAI :
    - Pilier 1 : Audio autonome (Whisper pur, sans LLM)
    - Pilier 2 : Contexte & RAG autonome (ChromaDB Vector Store)
    - Pilier 3 : Orchestrateur LLM universel (Prompt direct + Schema JSON strict, avec ou sans RAG)
    """

    # =========================================================================
    # PILIER 1 : Moteur Audio Autonome (Speech-to-Text sans LLM)
    # =========================================================================
    def test_pilier_1_audio_standalone_without_llm(self):
        """Vérifie que le moteur audio fonctionne en mode pur Speech-to-Text sans solliciter de LLM."""
        provider = TranscriptionProvider(provider="mock")
        # llm_provider est explicitement None : aucun LLM connecté
        audio_service = AudioTranscriptionService(transcription_provider=provider, llm_provider=None)

        req = TranscribeRequest(
            audio_base64="ZHVtbXlfYXVkaW9fYnl0ZXM=",
            filename="call_recording.mp3",
            language="fr",
            enable_correction=False,  # Désactivation explicite de la correction LLM
            diarization=True,
            speaker_roles=["Conseiller", "Client"]
        )

        response = audio_service.process(audio_bytes=b"dummy_audio_bytes", request=req)

        self.assertEqual(response.status, "success")
        self.assertEqual(response.correction_status, "DISABLED")
        self.assertIsNone(response.review_reason)
        self.assertGreater(response.duration_seconds, 0)
        self.assertGreater(len(response.segments), 0)
        self.assertTrue(len(response.speakers) > 0)
        self.assertGreater(response.structure.word_count, 0)
        self.assertGreater(response.structure.paragraph_count, 0)

    # =========================================================================
    # PILIER 2 : Moteur Contexte & RAG Autonome (Vector Store sans LLM)
    # =========================================================================
    def test_pilier_2_rag_search_standalone(self):
        """Vérifie que le moteur RAG indexe et recherche de manière autonome sans LLM."""
        store = GenericVectorStore(collection_name="test_modular_kb")

        # Ingestion de documents
        docs = [
            "Directive 01 : Les frais de tenue de compte sont plafonnés à 1000 FCFA.",
            "Directive 02 : La procédure d'opposition sur carte bancaire doit être immédiate.",
            "Règlement RH : Tout congé payé doit être posé 15 jours à l'avance."
        ]
        metadatas = [
            {"domaine": "banque", "type": "tarif"},
            {"domaine": "banque", "type": "carte"},
            {"domaine": "rh", "type": "conges"}
        ]
        ids = ["doc_01", "doc_02", "doc_03"]

        store.upsert_documents(docs, metadatas, ids)
        self.assertGreaterEqual(store.count(), 3)

        # Recherche sémantique autonome avec filtrage de métadonnées
        search_results = store.search(
            query="Comment bloquer ma carte bancaire ?",
            top_k=2,
            filter_metadata={"domaine": "banque"}
        )

        self.assertGreater(len(search_results), 0)
        top_match = search_results[0]
        self.assertIn("document", top_match)
        self.assertIn("similarity_score", top_match)
        self.assertEqual(top_match["metadata"]["domaine"], "banque")

    # =========================================================================
    # PILIER 3 : Orchestrateur LLM Universel Autonome (Prompt + Schema SANS RAG)
    # =========================================================================
    @patch("src.orchestrator.requests.post")
    def test_pilier_3_orchestrator_standalone_without_rag(self, mock_post):
        """Vérifie que l'Orchestrateur exécute un Use Case par Prompt + Schéma JSON strict sans RAG."""
        mock_post.return_value = MagicMock(status_code=200)

        orchestrator = Orchestrator()
        # Mock du provider LLM
        expected_json = '{"sentiment": "tres_negatif", "urgence": "GRAVE", "categorie": "LITIGE"}'
        orchestrator.provider = DummyLlmProvider(response_text=f"```json\n{expected_json}\n```")

        payload = {
            "module_key": "custom_module",
            "use_case_key": "qualification_directe",
            "system_prompt": "Analyse le texte du dossier soumis. Identifie le sentiment, le niveau d'urgence et la catégorie.",
            "input": {
                "texte_dossier": "Mon compte a été débité sans mon autorisation hier soir !"
            },
            "rag_config": {
                "enabled": False
            },
            "output_schema": [
                {"name": "sentiment", "type": "string", "description": "Tonalité globale"},
                {"name": "urgence", "type": "string", "description": "Niveau de sévérité"},
                {"name": "categorie", "type": "string", "description": "Classification"}
            ]
        }

        result = orchestrator.execute(payload)

        self.assertEqual(result["status"], "success")
        self.assertFalse(result["rag_context_used"])
        # Vérifier que les balises markdown ```json ont été nettoyées
        self.assertEqual(result["result"], expected_json)
        parsed = json.loads(result["result"])
        self.assertEqual(parsed["urgence"], "GRAVE")
        self.assertEqual(parsed["categorie"], "LITIGE")

    # =========================================================================
    # PILIER 3 : Orchestrateur LLM Universel avec Injection Contexte RAG
    # =========================================================================
    @patch("src.orchestrator.requests.post")
    def test_pilier_3_orchestrator_with_rag_context_injection(self, mock_post):
        """Vérifie que l'Orchestrateur injecte dynamiquement le contexte RAG dans le Prompt."""
        mock_post.return_value = MagicMock(status_code=200)

        orchestrator = Orchestrator()
        dummy_llm = DummyLlmProvider(response_text='{"solutions": ["Appliquer la directive 02"], "justification": "Conforme"}')
        orchestrator.provider = dummy_llm

        # Alimenter le store temporaire
        store = orchestrator.get_vector_store("kb_directives_test")
        store.upsert_documents(
            documents=["Directive carte 02 : Opposition sous 24h avec remboursement sous 48h."],
            metadatas=[{"type": "reglement"}],
            ids=["dir_02"]
        )

        payload = {
            "module_key": "banque_test",
            "use_case_key": "resolution_reglementaire",
            "system_prompt": "Tu es un expert. Voici le contexte réglementaire disponible :\n{context}\nPropose une solution au problème.",
            "input": {
                "plainte": "Carte bancaire débitée frauduleusement."
            },
            "rag_config": {
                "enabled": True,
                "collection": "kb_directives_test",
                "top_k": 1
            },
            "output_schema": [
                {"name": "solutions", "type": "array", "description": "Solutions recommandées"},
                {"name": "justification", "type": "string", "description": "Motif appuyé"}
            ]
        }

        result = orchestrator.execute(payload)

        self.assertEqual(result["status"], "success")
        self.assertTrue(result["rag_context_used"])
        # Vérifier que le contexte a bien été injecté dans le prompt envoyé au LLM
        self.assertIn("Directive carte 02", dummy_llm.last_system_prompt)
        self.assertIn("CRITICAL INSTRUCTION: You MUST return your answer in raw JSON format", dummy_llm.last_system_prompt)


if __name__ == "__main__":
    unittest.main()
