import re
import unicodedata
from typing import Tuple, Dict

class SentimentAnalyzer:
    """
    Analyseur de tonalité et sentiment agnostique du domaine.
    Calcule un score de polarité normalisé entre -1.0 et +1.0
    et qualifie la tonalité : 'tres_negatif', 'negatif', 'neutre', 'positif'.
    """

    # Lexique de valence générale (agnostique du métier)
    POSITIVE_WORDS = {
        "bon", "bien", "excellent", "super", "parfait", "merci", "remercie", "satisfait",
        "agreable", "rapide", "efficace", "felicitations", "bravo", "content", "aide",
        "resolu", "professionnel", "qualite", "solution", "parfaite", "formidable", "impeccable",
        "good", "great", "excellent", "satisfied", "happy", "thanks", "resolved", "fast"
    }

    NEGATIVE_WORDS = {
        "mauvais", "nul", "lent", "incompetent", "probleme", "erreur", "defaut", "echec",
        "panne", "decu", "insatisfait", "deception", "retard", "attente", "inadmissible",
        "scandale", "honte", "inacceptable", "colere", "furieux", "arnaque", "catastrophe",
        "grave", "voleur", "refus", "mensonge", "insatisfaction", "bloque", "perte", "perdu",
        "bad", "terrible", "slow", "error", "failed", "unhappy", "angry", "broken", "issue"
    }

    HIGH_ANGER_WORDS = {
        "scandale", "inadmissible", "honte", "inacceptable", "voleur", "arnaqueur",
        "furieux", "outre", "incompetents", "foutage", "catastrophique", "deception"
    }

    INTENSIFIERS = {
        "tres", "vraiment", "extremement", "trop", "tellement", "absolument", "completement",
        "totalement", "terriblement", "infiniment", "very", "extremely", "totally"
    }

    NEGATIONS = {
        "pas", "plus", "jamais", "aucun", "aucune", "rien", "nullement", "guere",
        "not", "never", "no", "none"
    }

    @staticmethod
    def _strip_accents(text: str) -> str:
        nfkd = unicodedata.normalize('NFKD', text.lower())
        return "".join([c for c in nfkd if not unicodedata.combining(c)])

    def analyze(self, text: str) -> Tuple[str, float]:
        """
        Analyse le texte et retourne (sentiment_label, polarity_score).
        Labels : 'tres_negatif', 'negatif', 'neutre', 'positif'.
        """
        if not text or not text.strip():
            return "neutre", 0.0

        normalized = self._strip_accents(text)
        words = re.findall(r"\b\w+\b", normalized)

        if not words:
            return "neutre", 0.0

        score = 0.0
        negated = False
        has_high_anger = any(w in self.HIGH_ANGER_WORDS for w in words)

        for i, word in enumerate(words):
            # Vérifier si le mot précédent était une négation
            is_negated = False
            if i > 0 and words[i - 1] in self.NEGATIONS:
                is_negated = True
            elif i > 1 and words[i - 2] in self.NEGATIONS:
                is_negated = True

            # Vérifier l'intensificateur
            intensity = 1.5 if (i > 0 and words[i - 1] in self.INTENSIFIERS) else 1.0

            if word in self.POSITIVE_WORDS:
                delta = 1.0 * intensity
                score += -delta if is_negated else delta
            elif word in self.NEGATIVE_WORDS:
                delta = -1.0 * intensity
                score += (delta * -0.5) if is_negated else delta

        # Normaliser le score par rapport au nombre de mots significatifs
        total_eval = max(1, len([w for w in words if w in self.POSITIVE_WORDS or w in self.NEGATIVE_WORDS]))
        normalized_score = max(-1.0, min(1.0, score / total_eval))

        # Pondération ponctuation (exclamation de colère / insatisfaction)
        exclamation_count = text.count('!')
        if exclamation_count >= 2 and normalized_score <= 0.0:
            normalized_score -= 0.2
            normalized_score = max(-1.0, normalized_score)

        # Qualification
        if normalized_score < -0.35 or has_high_anger:
            label = "tres_negatif"
        elif normalized_score < -0.05:
            label = "negatif"
        elif normalized_score > 0.15:
            label = "positif"
        else:
            label = "neutre"

        return label, round(normalized_score, 3)
