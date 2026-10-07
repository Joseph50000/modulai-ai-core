import base64
import logging
import time
from typing import Any, Dict, Optional

from .diarization_helper import apply_diarization
from .phonetic_corrector import PhoneticCorrector
from .schemas import AudioSegment, TextStructure, TranscribeRequest, TranscribeResponse
from .structure_helper import structure_transcription
from .transcription_provider import TranscriptionProvider

logger = logging.getLogger(__name__)


class AudioTranscriptionService:
    """Service d'orchestration pour le pipeline audio générique de ModulAI."""

    def __init__(self, transcription_provider: Optional[TranscriptionProvider] = None, llm_provider: Any = None):
        self.transcription_provider = transcription_provider or TranscriptionProvider()
        self.phonetic_corrector = PhoneticCorrector(llm_provider=llm_provider)

    def process(
        self,
        audio_bytes: bytes,
        request: TranscribeRequest,
    ) -> TranscribeResponse:
        start_time = time.time()
        logger.info(
            "[AUDIO_SERVICE] Traitement audio démarré (taille: %d octets, langue: %s, use_case: %s)",
            len(audio_bytes),
            request.language,
            request.use_case_key,
        )

        # 1. Transcription Whisper
        transcription_result = self.transcription_provider.transcribe(
            audio_bytes=audio_bytes,
            filename=request.filename or "audio.mp3",
            language=request.language or "fr",
        )

        raw_text = transcription_result.get("text", "")
        duration = transcription_result.get("duration")
        raw_segments = transcription_result.get("segments", [])

        # 2. Correction phonétique & lexicale via LLM
        final_text = raw_text
        correction_status = "DISABLED"
        review_reason = None

        if request.enable_correction and (request.vocabulary_terms or request.custom_correction_prompt):
            correction_res = self.phonetic_corrector.correct(
                text=raw_text,
                vocabulary_terms=request.vocabulary_terms,
                custom_prompt=request.custom_correction_prompt,
            )
            correction_status = correction_res.get("status", "DISABLED")
            review_reason = correction_res.get("review_reason")

            # Si la correction a été appliquée sans blocage d'intégrité, on utilise le texte corrigé
            if correction_status == "APPLIED":
                final_text = correction_res.get("text", raw_text)
            elif correction_status == "REVIEW_REQUIRED":
                # En cas de validation requise, on conserve le texte brut et on alerte
                final_text = raw_text

        # 3. Diarisation des locuteurs
        speakers = []
        segments = raw_segments
        if request.diarization or request.speaker_roles:
            diarization_res = apply_diarization(raw_segments, speaker_roles=request.speaker_roles)
            segments = diarization_res.get("segments", raw_segments)
            speakers = diarization_res.get("speakers", [])

        # 4. Structuration en paragraphes et statistiques
        structured_info = structure_transcription(final_text, segments=segments)

        exec_time_ms = int((time.time() - start_time) * 1000)

        # Formatage des segments Pydantic
        pydantic_segments = [
            AudioSegment(
                id=seg.get("id"),
                start=seg.get("start"),
                end=seg.get("end"),
                speaker=seg.get("speaker"),
                text=seg.get("text", ""),
            )
            for seg in segments
        ]

        structure_obj = TextStructure(
            paragraphs=structured_info.get("paragraphs", []),
            paragraph_count=structured_info.get("paragraph_count", 0),
            sentence_count=structured_info.get("sentence_count", 0),
            word_count=structured_info.get("word_count", 0),
            character_count=structured_info.get("character_count", 0),
        )

        logger.info(
            "[AUDIO_SERVICE] Traitement audio terminé avec succès en %d ms (correction: %s)",
            exec_time_ms,
            correction_status,
        )

        return TranscribeResponse(
            status="success",
            text=final_text,
            raw_text=raw_text,
            correction_status=correction_status,
            review_reason=review_reason,
            duration_seconds=duration,
            segments=pydantic_segments,
            speakers=speakers,
            structure=structure_obj,
            execution_time_ms=exec_time_ms,
        )
