import re
import logging
from typing import Optional

logger = logging.getLogger(__name__)

class SummaryGenerator:
    """
    Générateur de synthèse textuelle (extractif rapide ou abstractif LLM).
    """

    def generate_extractive(self, text: str, max_words: int = 50) -> str:
        """
        Extraction rapide basée sur la première phrase et la conclusion.
        Exécution immédiate sans coût LLM.
        """
        if not text or not text.strip():
            return ""

        clean_text = text.strip()
        sentences = [s.strip() for s in re.split(r'(?<=[.!?])\s+', clean_text) if s.strip()]

        if not sentences:
            return clean_text[:200]

        if len(sentences) == 1:
            words = sentences[0].split()
            if len(words) <= max_words:
                return sentences[0]
            return " ".join(words[:max_words]) + "..."

        first = sentences[0]
        last = sentences[-1]

        # Si le texte a au moins 3 phrases, composer première + fin
        combined = f"{first} [...] {last}"
        words = combined.split()
        if len(words) > max_words:
            return " ".join(words[:max_words]) + "..."
        return combined

    def generate_abstractive(self, text: str, llm_provider, model: str = None, max_words: int = 50) -> str:
        """
        Génération abstractive concise via le LLM.
        """
        if not text or not text.strip() or not llm_provider:
            return self.generate_extractive(text, max_words)

        system_prompt = (
            f"Tu es un assistant de synthèse documentaire. "
            f"Rédige un résumé fidèle, objectif et direct du texte en {max_words} mots maximum. "
            f"Ne fais aucun préambule (ex: 'Ce texte parle de...'), va droit au but."
        )
        user_prompt = f"Texte à résumer :\n\"{text}\""

        try:
            summary = llm_provider.generate(system_prompt=system_prompt, user_prompt=user_prompt, model=model)
            return summary.strip()
        except Exception as e:
            logger.warning(f"Échec résumé abstractif LLM, repli sur extractif : {e}")
            return self.generate_extractive(text, max_words)
