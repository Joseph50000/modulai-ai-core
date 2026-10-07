import io
import logging
import os
from typing import Any, Dict, Optional
import requests

logger = logging.getLogger(__name__)

SUPPORTED_EXTENSIONS = {".mp3", ".wav", ".m4a", ".ogg", ".flac", ".webm", ".aac"}
DEFAULT_GROQ_URL = "https://api.groq.com/openai/v1/audio/transcriptions"
DEFAULT_GROQ_MODEL = "whisper-large-v3-turbo"


class TranscriptionProvider:
    """Fournisseur générique et multi-backend pour la transcription audio (Groq, OpenAI, mock)."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
        provider: Optional[str] = None,
    ):
        self.provider = (
            provider
            or os.getenv("AUDIO_TRANSCRIPTION_PROVIDER")
            or "groq"
        ).lower()
        self.api_key = (
            api_key
            or os.getenv("AUDIO_TRANSCRIPTION_API_KEY")
            or os.getenv("CLOUD_TRANSCRIPTION_API_KEY")
            or os.getenv("GROQ_API_KEY")
            or os.getenv("OPENAI_API_KEY")
            or ""
        )
        self.base_url = (
            base_url
            or os.getenv("AUDIO_TRANSCRIPTION_URL")
            or os.getenv("CLOUD_TRANSCRIPTION_URL")
            or DEFAULT_GROQ_URL
        )
        self.model = (
            model
            or os.getenv("AUDIO_TRANSCRIPTION_MODEL")
            or os.getenv("CLOUD_TRANSCRIPTION_MODEL")
            or DEFAULT_GROQ_MODEL
        )
        self.max_size_bytes = int(os.getenv("AUDIO_MAX_FILE_SIZE_MB", "25")) * 1024 * 1024

    def validate_audio(self, audio_bytes: bytes, filename: str) -> None:
        if not audio_bytes:
            raise ValueError("Le flux audio est vide.")
        if len(audio_bytes) > self.max_size_bytes:
            raise ValueError(
                f"Taille de fichier ({len(audio_bytes) / (1024*1024):.1f} Mo) dépasse la limite autorisée ({self.max_size_bytes / (1024*1024):.0f} Mo)."
            )
        ext = os.path.splitext(filename.lower())[1]
        if ext and ext not in SUPPORTED_EXTENSIONS:
            raise ValueError(f"Extension '{ext}' non supportée. Formats autorisés : {', '.join(sorted(SUPPORTED_EXTENSIONS))}")

    def transcribe(
        self,
        audio_bytes: bytes,
        filename: str = "audio.mp3",
        language: Optional[str] = "fr",
        prompt: Optional[str] = None,
        timeout_seconds: int = 60,
    ) -> Dict[str, Any]:
        """Transcrit les octets audio en texte brut et segments horodatés."""
        self.validate_audio(audio_bytes, filename)

        # Mode MOCK pour les tests automatisés sans clé API
        if self.provider == "mock":
            logger.info("[AUDIO_PROVIDER] Mode mock actif - simulation de transcription.")
            return {
                "text": "Ceci est une transcription simulée par le moteur audio de test.",
                "duration": 5.0,
                "segments": [
                    {"id": 0, "start": 0.0, "end": 2.5, "text": "Ceci est une transcription simulée", "speaker": "SPEAKER_00"},
                    {"id": 1, "start": 2.5, "end": 5.0, "text": "par le moteur audio de test.", "speaker": "SPEAKER_01"},
                ],
            }

        if not self.api_key:
            raise RuntimeError(
                "Aucune clé API de transcription configurée (AUDIO_TRANSCRIPTION_API_KEY ou GROQ_API_KEY requise)."
            )

        headers = {
            "Authorization": f"Bearer {self.api_key}",
        }

        # Déterminer le type MIME selon l'extension
        ext = os.path.splitext(filename.lower())[1].lstrip(".")
        mime_type = f"audio/{ext}" if ext != "mp3" else "audio/mpeg"

        files = {
            "file": (filename, io.BytesIO(audio_bytes), mime_type),
        }
        data = {
            "model": self.model,
            "response_format": "verbose_json",
        }
        if language:
            data["language"] = language
        if prompt:
            data["prompt"] = prompt

        try:
            logger.info("Envoi de la requête de transcription audio vers %s (modèle: %s)...", self.base_url, self.model)
            response = requests.post(
                self.base_url,
                headers=headers,
                files=files,
                data=data,
                timeout=timeout_seconds,
            )
            if not response.ok:
                error_detail = response.text
                try:
                    error_json = response.json()
                    error_detail = error_json.get("error", {}).get("message", error_detail)
                except Exception:
                    pass
                raise RuntimeError(f"Erreur API Transcription HTTP {response.status_code}: {error_detail}")

            result = response.json()
            raw_text = result.get("text", "").strip()
            duration = result.get("duration")

            # Normalisation des segments
            raw_segments = result.get("segments", [])
            segments = []
            for seg in raw_segments:
                segments.append({
                    "id": seg.get("id"),
                    "start": seg.get("start"),
                    "end": seg.get("end"),
                    "text": seg.get("text", "").strip(),
                    "speaker": seg.get("speaker"),
                })

            return {
                "text": raw_text,
                "duration": duration,
                "segments": segments,
            }

        except requests.RequestException as e:
            logger.error("Échec de la requête HTTP vers le fournisseur audio: %s", e)
            raise RuntimeError(f"Échec de connexion au service de transcription: {e}")
