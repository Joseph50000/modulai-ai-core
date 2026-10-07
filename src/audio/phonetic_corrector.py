import logging
import os
import re
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# Motifs d'information critique à ne jamais altérer lors d'une correction
_PROTECTED_PATTERNS = (
    r"\b\d[\d\s.,/-]*\b",  # Nombres, codes, montants
    r"\b(?:pas|jamais|aucun|aucune|sans|ne|n'|rien|personne)\b",  # Négations
    r"\b(?:euro|euros|dollar|dollars|chf|fcfa|xaf|f|cfa|%)\b",  # Devises et unités
    r"\b(?:jour|jours|semaine|semaines|mois|an|ans|année|années|heure|heures|minute|minutes)\b",  # Temporalité
)

DEFAULT_SYSTEM_PROMPT = """Tu es un assistant de correction de transcription audio.
Tu corriges la ponctuation, les majuscules, les fautes d'accord évidentes et adaptes l'orthographe selon la liste de termes fournie.
RÈGLES STRICTES :
1. Ne résume jamais, n'ajoute aucune interprétation et ne supprime aucune information.
2. Conserve rigoureusement tous les chiffres, nombres, dates, montants et négations (pas, jamais, aucun, sans, ne, n').
3. Si un mot ou passage est incertain ou inintelligible, conserve-le tel quel sans l'inventer.
4. Retourne UNIQUEMENT le texte corrigé brut, sans formule de politesse ni bloc markdown.
"""


def _protected_markers(text: str) -> List[str]:
    markers = []
    for pattern in _PROTECTED_PATTERNS:
        markers.extend(match.group(0).lower().strip() for match in re.finditer(pattern, text, re.IGNORECASE))
    return markers


def _needs_review(original: str, corrected: str) -> Optional[str]:
    original_markers = _protected_markers(original)
    corrected_lower = corrected.lower()
    missing = [marker for marker in original_markers if marker not in corrected_lower]
    if missing:
        unique_missing = list(dict.fromkeys(missing))
        return f"Informations protégées absentes après correction : {', '.join(unique_missing)}"
    return None


class PhoneticCorrector:
    """Service générique de correction phonétique et lexicale assistée par LLM."""

    def __init__(self, llm_provider=None):
        self.llm_provider = llm_provider

    def correct(
        self,
        text: str,
        vocabulary_terms: Optional[List[str]] = None,
        custom_prompt: Optional[str] = None,
        options: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Corrige la transcription en s'appuyant sur les termes de vocabulaire autorisés."""
        if not text or not text.strip():
            return {"text": text, "status": "EMPTY", "applied": False}

        terms = vocabulary_terms or []
        # Si aucun terme fourni et pas de prompt personnalisé, pas besoin d'altérer le texte
        if not terms and not custom_prompt:
            return {"text": text, "status": "DISABLED", "applied": False}

        if not self.llm_provider:
            logger.warning("[AUDIO_CORRECTION] Aucun fournisseur LLM fourni pour la correction.")
            return {"text": text, "status": "DISABLED", "applied": False}

        system_prompt = custom_prompt or DEFAULT_SYSTEM_PROMPT
        terms_str = ", ".join(terms)
        user_prompt = f"Termes métier autorisés : {terms_str}\n\nTranscription brute à corriger :\n{text}"

        try:
            logger.info("[AUDIO_CORRECTION] Lancement de la correction LLM (%d termes, %d caractères)...", len(terms), len(text))
            opts = options or {"temperature": 0.0}
            corrected = self.llm_provider.generate(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                options=opts,
            ).strip()

            # Nettoyage si le modèle a entouré de guillemets ou de markdown
            if corrected.startswith("```") and corrected.endswith("```"):
                lines = corrected.splitlines()
                if len(lines) >= 3:
                    corrected = "\n".join(lines[1:-1]).strip()

            if not corrected:
                return {"text": text, "status": "DISABLED", "applied": False}

            # Contrôle de sécurité et préservation des données critiques
            review_reason = _needs_review(text, corrected)
            if review_reason:
                logger.warning("[AUDIO_CORRECTION] Alerte de validation requise : %s", review_reason)
                return {
                    "text": text,
                    "status": "REVIEW_REQUIRED",
                    "applied": False,
                    "proposed_text": corrected,
                    "review_reason": review_reason,
                }

            applied = corrected != text
            logger.info("[AUDIO_CORRECTION] Correction réussie (modifié : %s).", applied)
            return {
                "text": corrected,
                "status": "APPLIED",
                "applied": applied,
            }

        except Exception as e:
            logger.error("[AUDIO_CORRECTION] Erreur lors de l'appel LLM : %s", e)
            return {
                "text": text,
                "status": "ERROR",
                "applied": False,
                "error": str(e),
            }
