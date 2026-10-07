import unittest
from src.audio.schemas import TranscribeRequest, TranscribeResponse
from src.audio.transcription_provider import TranscriptionProvider
from src.audio.phonetic_corrector import PhoneticCorrector
from src.audio.diarization_helper import apply_diarization
from src.audio.structure_helper import structure_transcription


class DummyLlmProvider:
    def __init__(self, response_text: str):
        self.response_text = response_text
        self.last_system_prompt = None
        self.last_user_prompt = None

    def generate(self, system_prompt: str, user_prompt: str, options: dict = None) -> str:
        self.last_system_prompt = system_prompt
        self.last_user_prompt = user_prompt
        return self.response_text


class AudioEngineTests(unittest.TestCase):
    def test_transcription_provider_mock(self):
        provider = TranscriptionProvider(provider="mock")
        result = provider.transcribe(b"fake_audio_bytes", filename="test.mp3")
        self.assertIn("text", result)
        self.assertGreater(result["duration"], 0)
        self.assertEqual(len(result["segments"]), 2)

    def test_transcription_provider_validation(self):
        provider = TranscriptionProvider(provider="mock")
        # Test flux vide
        with self.assertRaises(ValueError):
            provider.transcribe(b"", filename="empty.mp3")
        # Test extension interdite
        with self.assertRaises(ValueError):
            provider.transcribe(b"content", filename="virus.exe")

    def test_phonetic_corrector_applies_terms(self):
        mock_llm = DummyLlmProvider("Bonjour, je souhaite activer le protocole AéroSpace-X.")
        corrector = PhoneticCorrector(llm_provider=mock_llm)

        raw_text = "Bonjour, je souhaite activer le protocole aéro space x."
        vocab = ["AéroSpace-X", "Protocole-Beta"]

        res = corrector.correct(raw_text, vocabulary_terms=vocab)
        self.assertEqual(res["status"], "APPLIED")
        self.assertTrue(res["applied"])
        self.assertEqual(res["text"], "Bonjour, je souhaite activer le protocole AéroSpace-X.")
        self.assertIn("AéroSpace-X", mock_llm.last_user_prompt)

    def test_phonetic_corrector_integrity_protection(self):
        # Le mock LLM supprime malencontreusement le montant et la négation
        mock_llm = DummyLlmProvider("J'ai validé le transfert pour un montant.")
        corrector = PhoneticCorrector(llm_provider=mock_llm)

        # Texte original avec 500 euros et négation "pas"
        raw_text = "Je n'ai pas validé le transfert de 500 euros."
        vocab = ["Transfert-Express"]

        res = corrector.correct(raw_text, vocabulary_terms=vocab)
        # La protection d'intégrité doit bloquer l'écrasement silencieux
        self.assertEqual(res["status"], "REVIEW_REQUIRED")
        self.assertFalse(res["applied"])
        self.assertEqual(res["text"], raw_text)  # Le texte original est conservé
        self.assertIn("Informations protégées absentes", res["review_reason"])

    def test_diarization_with_custom_roles(self):
        raw_segments = [
            {"id": 0, "speaker": "SPEAKER_00", "text": "Bonjour, comment puis-je vous aider ?"},
            {"id": 1, "speaker": "SPEAKER_01", "text": "J'ai une question sur mon contrat."},
            {"id": 2, "speaker": "SPEAKER_00", "text": "Très bien, donnez-moi votre numéro."},
        ]

        # Test avec rôles personnalisés
        result = apply_diarization(raw_segments, speaker_roles=["Conseiller", "Client"])
        self.assertEqual(result["status"], "APPLIED")
        self.assertEqual(result["speakers"], ["Client", "Conseiller"])
        self.assertEqual(result["segments"][0]["speaker"], "Conseiller")
        self.assertEqual(result["segments"][1]["speaker"], "Client")
        self.assertEqual(result["segments"][2]["speaker"], "Conseiller")

    def test_structure_helper(self):
        text = "Première phrase ici. Deuxième phrase là. Et voilà une troisième phrase."
        segments = [
            {"id": 0, "start": 0.0, "end": 2.0, "text": "Première phrase ici.", "speaker": "A"},
            {"id": 1, "start": 2.1, "end": 4.0, "text": "Deuxième phrase là.", "speaker": "B"},
            {"id": 2, "start": 4.1, "end": 6.0, "text": "Et voilà une troisième phrase.", "speaker": "A"},
        ]

        structured = structure_transcription(text, segments=segments, max_paragraph_chars=100)
        self.assertGreater(structured["paragraph_count"], 0)
        self.assertEqual(structured["sentence_count"], 3)
        self.assertGreater(structured["word_count"], 5)
        self.assertEqual(structured["character_count"], len(text))

    def test_audio_transcription_service_e2e(self):
        from src.audio import AudioTranscriptionService, TranscribeRequest

        mock_provider = TranscriptionProvider(provider="mock")
        mock_llm = DummyLlmProvider("Ceci est une transcription simulée par le moteur audio de test corrigé.")
        service = AudioTranscriptionService(transcription_provider=mock_provider, llm_provider=mock_llm)

        req = TranscribeRequest(
            filename="sample.mp3",
            enable_correction=True,
            vocabulary_terms=["simulée", "moteur audio"],
            diarization=True,
            speaker_roles=["Opérateur", "Client"],
        )

        response = service.process(b"fake_audio_content", req)
        self.assertEqual(response.status, "success")
        self.assertEqual(response.correction_status, "APPLIED")
        self.assertGreater(len(response.segments), 0)
        self.assertEqual(response.segments[0].speaker, "Opérateur")
        self.assertGreater(response.structure.word_count, 0)
        self.assertGreaterEqual(response.execution_time_ms, 0)

    def test_audio_endpoint_handler(self):
        import base64
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from src.audio import AudioTranscriptionService, TranscribeRequest, TranscribeResponse

        test_app = FastAPI()
        mock_provider = TranscriptionProvider(provider="mock")
        service = AudioTranscriptionService(transcription_provider=mock_provider)

        @test_app.post("/api/audio/transcribe", response_model=TranscribeResponse)
        def endpoint(payload: TranscribeRequest):
            raw = base64.b64decode(payload.audio_base64)
            return service.process(raw, payload)

        client = TestClient(test_app)
        audio_b64 = base64.b64encode(b"dummy_audio_bytes").decode("utf-8")

        payload = {
            "audio_base64": audio_b64,
            "filename": "audio.mp3",
            "enable_correction": False,
            "diarization": True,
            "speaker_roles": ["Agent", "Usager"],
        }

        res = client.post("/api/audio/transcribe", json=payload)
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["status"], "success")
        self.assertIn("text", data)
        self.assertIn("raw_text", data)
        self.assertGreater(len(data["segments"]), 0)
        self.assertEqual(data["segments"][0]["speaker"], "Agent")


if __name__ == "__main__":
    unittest.main()
