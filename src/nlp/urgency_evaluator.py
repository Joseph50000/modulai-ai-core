import json
import logging
from typing import List, Dict, Any, Tuple, Optional

logger = logging.getLogger(__name__)

class UrgencyEvaluator:
    """
    Évaluateur d'urgence et de gravité paramétrable (Chain-of-Thought LLM + Heuristique).
    L'échelle d'urgence (ex: MINEUR, MOYEN, GRAVE) est entièrement configurable.
    """

    def __init__(self, llm_provider=None):
        self.llm_provider = llm_provider

    def evaluate(
        self,
        text: str,
        urgency_levels: List[str] = None,
        taxonomy: Optional[Dict[str, Any]] = None,
        sensitive_keywords_detected: List[str] = None,
        sentiment: str = "neutre",
        context_nature: str = "DOSSIER",
        context_definition: str = "",
        model: Optional[str] = None
    ) -> Tuple[str, str]:
        """
        Évalue le niveau d'urgence.
        Retourne (urgency_level, reasoning).
        """
        levels = urgency_levels or ["MINEUR", "MOYEN", "GRAVE"]
        lowest_level = levels[0]
        intermediate_level = levels[len(levels) // 2] if len(levels) > 1 else levels[0]
        highest_level = levels[-1]

        detected_kw = sensitive_keywords_detected or []
        word_count = len(text.split())

        # Repli immédiat si le texte est très court (< 5 mots)
        if word_count < 5:
            if detected_kw:
                return highest_level, f"Urgence élevée suite à la détection de termes sensibles : {', '.join(detected_kw)}"
            if text.count('!') >= 2 or sentiment == "tres_negatif":
                return intermediate_level, "Urgence intermédiaire : tonalité vive ou ponctuation d'insistance détectée"
            return lowest_level, "Texte court sans indicateur critique détecté"

        # Stratégie LLM Chain-of-Thought si disponible
        if self.llm_provider:
            try:
                from src.nlp.hierarchical_classifier import HierarchicalClassifier
                tree_text = HierarchicalClassifier.format_taxonomy_tree(taxonomy) if taxonomy else ""

                system_prompt = (
                    f"Tu es un assistant expert en priorisation et évaluation d'urgence pour la gestion de dossiers.\n"
                    f"Ton rôle est d'analyser le texte d'un dossier et d'évaluer son niveau d'urgence selon l'échelle suivante : "
                    f"[{', '.join(levels)}].\n"
                    f"RÈGLES :\n"
                    f"1. Réfère-toi aux descriptions et aux niveaux de gravité des éléments de la taxonomie si fournis.\n"
                    f"2. Rédige d'abord une 'analyse_du_probleme' en 1 phrase expliquant objectivement la sévérité.\n"
                    f"3. Le champ 'urgence' DOIT être EXACTEMENT l'une des valeurs suivantes : {', '.join(levels)}.\n"
                    f"4. Réponds UNIQUEMENT avec un JSON valide : {{\"analyse_du_probleme\": \"...\", \"urgence\": \"...\"}}"
                )

                user_prompt = (
                    f"Nature du contexte : '{context_nature}'\n"
                    f"Définition du contexte : '{context_definition}'\n"
                    f"Mots sensibles identifiés : {detected_kw}\n"
                    f"Sentiment détecté : {sentiment}\n"
                    f"Texte soumis :\n\"{text}\"\n\n"
                    f"Taxonomie et niveaux de référence :\n{tree_text}\n"
                )

                raw_response = self.llm_provider.generate(
                    system_prompt=system_prompt,
                    user_prompt=user_prompt,
                    model=model,
                    options={'temperature': 0}
                )

                clean_json = raw_response.strip()
                if clean_json.startswith("```"):
                    clean_json = clean_json.split("\n", 1)[-1].rsplit("```", 1)[0].strip()

                parsed = json.loads(clean_json)
                target_urgency = str(parsed.get("urgence", lowest_level)).strip().upper()
                reasoning = parsed.get("analyse_du_probleme") or "Évaluation d'urgence effectuée par le LLM"

                # Validation de conformité avec les niveaux configurés
                for level in levels:
                    if level.upper() == target_urgency or level.upper() in target_urgency:
                        return level, reasoning

                # Si le format retourné ne correspond pas exactement, chercher le niveau le plus proche
                return lowest_level, reasoning
            except Exception as e:
                logger.warning(f"Échec de l'évaluation d'urgence LLM ({e}), repli heuristique")

        # Repli heuristique basé sur les mots sensibles et le sentiment
        if len(detected_kw) >= 2 or (detected_kw and sentiment in ["negatif", "tres_negatif"]):
            return highest_level, f"Urgence critique basée sur les termes sensibles : {', '.join(detected_kw)}"
        if detected_kw or sentiment == "tres_negatif" or text.count('!') >= 2:
            return intermediate_level, "Urgence intermédiaire basée sur la tonalité ou la présence de mots sensibles"

        return lowest_level, "Urgence standard sans facteur aggravant détecté"
