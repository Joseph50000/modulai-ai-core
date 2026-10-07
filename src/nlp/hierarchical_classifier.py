import json
import logging
from typing import Dict, Any, Tuple, Optional

logger = logging.getLogger(__name__)

class HierarchicalClassifier:
    """
    Classifieur hiérarchique Zero-Shot guidé par une taxonomie dynamique (Parent > Enfant).
    Agnostique de tout domaine métier : la taxonomie est injectée à l'exécution.
    """

    def __init__(self, llm_provider=None):
        self.llm_provider = llm_provider

    @staticmethod
    def format_taxonomy_tree(taxonomy: Optional[Dict[str, Any]]) -> str:
        """
        Convertit un dictionnaire ou une structure de taxonomie en texte descriptif
        compréhensible par le LLM.
        """
        if not taxonomy:
            return ""

        tree_lines = []
        for cat_key, cat_data in taxonomy.items():
            cat_desc = ""
            subcategories = []

            if hasattr(cat_data, "description"):
                cat_desc = cat_data.description or ""
                subcategories = getattr(cat_data, "subcategories", []) or getattr(cat_data, "motifs", [])
            elif isinstance(cat_data, dict):
                cat_desc = cat_data.get("description", "") or ""
                subcategories = cat_data.get("subcategories") or cat_data.get("motifs") or []

            desc_part = f" (Description: {cat_desc})" if cat_desc else ""
            tree_lines.append(f"- Catégorie '{cat_key}'{desc_part} :")

            for sub in subcategories:
                s_label = ""
                s_desc = ""
                s_sev = ""

                if hasattr(sub, "label") or hasattr(sub, "libelle"):
                    s_label = getattr(sub, "label", None) or getattr(sub, "libelle", "")
                    s_desc = getattr(sub, "description", "") or ""
                    s_sev = getattr(sub, "severity", None) or getattr(sub, "gravite", "") or ""
                elif isinstance(sub, dict):
                    s_label = sub.get("label") or sub.get("libelle") or ""
                    s_desc = sub.get("description", "") or ""
                    s_sev = sub.get("severity") or sub.get("gravite") or ""

                details = []
                if s_desc:
                    details.append(f"Description: {s_desc}")
                if s_sev:
                    details.append(f"Niveau/Gravité: {s_sev}")

                detail_str = f" -> {', '.join(details)}" if details else ""
                tree_lines.append(f"    * Élément: '{s_label}'{detail_str}")

        return "\n".join(tree_lines)

    def classify(
        self,
        text: str,
        taxonomy: Optional[Dict[str, Any]] = None,
        context_nature: str = "DOSSIER",
        context_definition: str = "",
        model: Optional[str] = None
    ) -> Tuple[str, str, str]:
        """
        Exécute la classification via LLM avec parsing JSON strict et température 0.
        Retourne (category, subcategory, reasoning).
        """
        if not taxonomy:
            return "AUTRE", "AUTRE", "Aucune taxonomie fournie pour la classification"

        tree_text = self.format_taxonomy_tree(taxonomy)

        system_prompt = (
            f"Tu es un assistant expert en classification sémantique et analyse documentaire.\n"
            f"Ton rôle est d'analyser le texte soumis et de le classifier précisément selon l'arborescence fournie.\n"
            f"Tu dois choisir la CATÉGORIE principale et le SOUS-ÉLÉMENT spécifique le plus approprié.\n"
            f"RÈGLES STRICTES :\n"
            f"1. Le sous-élément DOIT impérativement appartenir à la catégorie parente choisie.\n"
            f"2. Si le texte ne correspond à aucune catégorie/élément listé, ou s'il s'agit d'une demande hors-sujet, "
            f"tu dois renvoyer 'AUTRE' pour la catégorie et 'AUTRE' pour le sous-élément.\n"
            f"3. Réponds UNIQUEMENT avec un objet JSON valide, sans texte additionnel ni markdown.\n"
            f"4. Format JSON attendu : {{\"analyse_du_probleme\": \"<1-2 phrases explicatives>\", \"category\": \"<nom_categorie>\", \"subcategory\": \"<nom_sous_element>\"}}"
        )

        user_prompt = (
            f"Nature du contexte : '{context_nature}'\n"
            f"Définition du contexte : '{context_definition}'\n"
            f"Texte soumis :\n\"{text}\"\n\n"
            f"Taxonomie disponible :\n{tree_text}\n"
        )

        if not self.llm_provider:
            return self._heuristic_fallback(text, taxonomy)

        try:
            raw_response = self.llm_provider.generate(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                model=model,
                options={'temperature': 0}
            )

            # Nettoyer d'éventuels backticks markdown JSON
            clean_json = raw_response.strip()
            if clean_json.startswith("```"):
                clean_json = clean_json.split("\n", 1)[-1].rsplit("```", 1)[0].strip()

            parsed = json.loads(clean_json)
            cat = parsed.get("category") or parsed.get("Category") or parsed.get("categorie") or "AUTRE"
            sub = parsed.get("subcategory") or parsed.get("Subcategory") or parsed.get("motif") or parsed.get("Motif") or "AUTRE"
            reason = parsed.get("analyse_du_probleme") or parsed.get("raisonnement") or parsed.get("reasoning") or "Aucune explication"

            return str(cat).strip(), str(sub).strip(), str(reason).strip()
        except Exception as e:
            logger.warning(f"Échec de la classification LLM ({e}), repli sur fallback heuristique")
            return self._heuristic_fallback(text, taxonomy)

    def _heuristic_fallback(self, text: str, taxonomy: Dict[str, Any]) -> Tuple[str, str, str]:
        """Repli par correspondance lexicale sur les libellés de la taxonomie si le LLM est indisponible."""
        text_lower = text.lower()
        best_cat = "AUTRE"
        best_sub = "AUTRE"
        best_score = 0

        for cat_key, cat_data in taxonomy.items():
            cat_score = 1 if cat_key.lower() in text_lower else 0
            subcategories = []
            if hasattr(cat_data, "subcategories"):
                subcategories = cat_data.subcategories or []
            elif isinstance(cat_data, dict):
                subcategories = cat_data.get("subcategories") or cat_data.get("motifs") or []

            for sub in subcategories:
                label = getattr(sub, "label", None) or getattr(sub, "libelle", None) if hasattr(sub, "label") or hasattr(sub, "libelle") else (sub.get("label") or sub.get("libelle") if isinstance(sub, dict) else "")
                if label and label.lower() in text_lower:
                    score = cat_score + 2
                    if score > best_score:
                        best_score = score
                        best_cat = cat_key
                        best_sub = label

        reason = "Classification par correspondance lexicale de secours" if best_cat != "AUTRE" else "Aucune correspondance trouvée"
        return best_cat, best_sub, reason
