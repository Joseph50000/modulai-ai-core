from typing import List, Dict, Any, Optional

class ContextAggregator:
    """
    Agrégateur de double contexte RAG (Historique/Transactionnel + Documentaire/Réglementaire).
    Agnostique du domaine métier : structure les extraits sous un format clair pour le LLM.
    """

    @staticmethod
    def extract_solution_text(item: Dict[str, Any], target_field: Optional[str] = None) -> str:
        """Extrait le texte de la solution depuis les métadonnées ou le document."""
        meta = item.get("metadata", {})
        if target_field and meta.get(target_field):
            return str(meta.get(target_field))

        # Champs usuels agnostiques
        for candidate in ["solution", "solution_retenue", "resolution", "action_prise", "reponse", "reponse_historique"]:
            if meta.get(candidate):
                return str(meta.get(candidate))

        return str(item.get("document", ""))

    def format_historical_context(
        self,
        historical_items: List[Dict[str, Any]],
        target_solution_field: Optional[str] = None
    ) -> str:
        if not historical_items:
            return "Aucun cas historique similaire trouvé."

        lines = []
        for i, item in enumerate(historical_items):
            doc_text = item.get("document", "").strip()
            sol_text = self.extract_solution_text(item, target_solution_field).strip()
            similarity = item.get("similarity_score", 0.0)

            lines.append(
                f"- Cas similaire {i+1} (Pertinence: {similarity:.2f}) :\n"
                f"  Situation : {doc_text}\n"
                f"  Solution/Action retenue : {sol_text}"
            )
        return "\n".join(lines)

    def format_documentary_context(self, documentary_items: List[Dict[str, Any]]) -> str:
        if not documentary_items:
            return "Aucune documentation de référence applicable trouvée."

        lines = []
        for i, item in enumerate(documentary_items):
            meta = item.get("metadata", {})
            title = meta.get("title") or meta.get("document_name") or f"Document {i+1}"
            doc_text = item.get("document", "").strip()
            similarity = item.get("similarity_score", 0.0)

            lines.append(
                f"- Référence {i+1} [{title}] (Pertinence: {similarity:.2f}) :\n"
                f"  {doc_text}"
            )
        return "\n".join(lines)

    def format_combined_context(
        self,
        historical_items: List[Dict[str, Any]],
        documentary_items: List[Dict[str, Any]],
        target_solution_field: Optional[str] = None
    ) -> str:
        parts = []
        if historical_items:
            parts.append("--- CAS ET SOLUTIONS HISTORIQUES SIMILAIRES ---")
            parts.append(self.format_historical_context(historical_items, target_solution_field))

        if documentary_items:
            parts.append("--- CADRE DE RÉFÉRENCE ET DOCUMENTATION APPLICABLE ---")
            parts.append(self.format_documentary_context(documentary_items))

        if not parts:
            return "Aucun contexte historique ou documentaire trouvé."

        return "\n\n".join(parts)
