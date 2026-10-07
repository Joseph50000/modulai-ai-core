import re
import unicodedata
from typing import List

class SensitiveWordsDetector:
    """
    Détecteur générique et agnostique de mots sensibles/critiques.
    Ne contient AUCUN mot codé en dur : la liste de termes est injectée dynamiquement.
    """

    @staticmethod
    def _normalize(text: str) -> str:
        """Supprime les accents et convertit en minuscules."""
        if not text:
            return ""
        nfkd = unicodedata.normalize('NFKD', text.lower())
        return "".join([c for c in nfkd if not unicodedata.combining(c)])

    def detect(self, text: str, sensitive_keywords: List[str] = None) -> List[str]:
        """
        Détecte la présence des termes de la liste dynamique dans le texte.
        Supporte les flexions courantes (pluriels 's', féminins 'e', participes/infinitifs).
        """
        if not text or not sensitive_keywords:
            return []

        text_norm = self._normalize(text)
        detected = []

        for keyword in sensitive_keywords:
            raw_keyword = keyword.strip()
            if not raw_keyword:
                continue

            kw_norm = self._normalize(raw_keyword)
            if kw_norm.endswith("al"):
                stem = kw_norm[:-2]
                pattern = rf"\b(?:{re.escape(kw_norm)}(?:e|ee|er|es|ees|s)?|{re.escape(stem)}aux)\b"
            else:
                pattern = rf"\b{re.escape(kw_norm)}(?:e|ee|er|es|ees|s|x)?\b"
            
            if re.search(pattern, text_norm):
                detected.append(raw_keyword)

        return list(dict.fromkeys(detected))
