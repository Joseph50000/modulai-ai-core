import re
import logging
from typing import List, Dict, Any, Tuple, Optional, Generator
from src.rag.schemas import PropositionItem

logger = logging.getLogger(__name__)

class ResolutionEngine:
    """
    Moteur de recommandation et résolution générique assistée par RAG.
    Agnostique du domaine : construit des propositions structurées basées sur
    l'historique des cas similaires et le cadre documentaire fourni.
    """

    def __init__(self, llm_provider=None):
        self.llm_provider = llm_provider

    def build_prompts(
        self,
        query: str,
        historical_context: str,
        documentary_context: str,
        combined_context: str,
        num_propositions: int = 3,
        system_role_instruction: Optional[str] = None,
        custom_resolution_prompt: Optional[str] = None
    ) -> Tuple[str, str]:
        role = system_role_instruction or "Tu es un assistant expert en résolution de dossiers et aide à la décision opérationnelle."

        if custom_resolution_prompt:
            # Si un template surchargé est fourni
            system_prompt = custom_resolution_prompt
        else:
            system_prompt = (
                f"{role}\n"
                f"Ton rôle est d'analyser la situation soumise en t'appuyant rigoureusement sur les cas historiques "
                f"similaires et le cadre documentaire de référence fournis.\n\n"
                f"Règles strictes :\n"
                f"1. Rédige d'abord une courte analyse (raisonnement) en 1 ou 2 phrases de la situation, préfixée EXACTEMENT par 'RAISONNEMENT :'.\n"
                f"2. Ensuite, propose EXACTEMENT {num_propositions} options ou actions recommandées, numérotées de 1 à {num_propositions}.\n"
                f"3. Format strict pour chaque proposition par ligne : 'N. [Action / Solution recommandée] | [Justification / Commentaire pour l'agent]'.\n"
                f"4. Reste professionnel, direct et constructif. Ne mentionne pas que tu es une intelligence artificielle."
            )

        user_prompt = (
            f"Cas / Situation soumis :\n\"{query}\"\n\n"
            f"{combined_context}\n\n"
            f"Rédige maintenant ton analyse (RAISONNEMENT :) suivie des {num_propositions} propositions au format 'N. [Action] | [Justification]'."
        )

        return system_prompt, user_prompt

    def parse_propositions(self, generated_text: str) -> Tuple[Optional[str], List[PropositionItem]]:
        """Découpe le texte généré pour extraire le raisonnement et les propositions typées."""
        if not generated_text:
            return None, []

        reasoning = None
        propositions: List[PropositionItem] = []

        # Extraction du raisonnement préfixé
        match_reasoning = re.search(r"RAISONNEMENT\s*:\s*(.*?)(?=\n\s*\d+[\.\)]|\Z)", generated_text, re.DOTALL | re.IGNORECASE)
        if match_reasoning:
            reasoning = match_reasoning.group(1).strip()

        # Extraction des lignes numérotées
        lines = generated_text.splitlines()
        for line in lines:
            line_str = line.strip()
            match_item = re.match(r"^(\d+)[\.\)]\s*(.*)", line_str)
            if match_item:
                idx = int(match_item.group(1))
                content = match_item.group(2).strip()

                if "|" in content:
                    parts = content.split("|", 1)
                    title = parts[0].strip()
                    details = parts[1].strip()
                else:
                    title = content
                    details = None

                propositions.append(PropositionItem(index=idx, title=title, details=details))

        return reasoning, propositions

    def resolve(
        self,
        query: str,
        historical_context: str,
        documentary_context: str,
        combined_context: str,
        num_propositions: int = 3,
        system_role_instruction: Optional[str] = None,
        custom_resolution_prompt: Optional[str] = None,
        model: Optional[str] = None
    ) -> Tuple[Optional[str], List[PropositionItem], str]:
        """Exécution synchrone de la résolution."""
        if not self.llm_provider:
            return None, [], "Aucun provider LLM configuré pour générer des recommandations."

        system_prompt, user_prompt = self.build_prompts(
            query=query,
            historical_context=historical_context,
            documentary_context=documentary_context,
            combined_context=combined_context,
            num_propositions=num_propositions,
            system_role_instruction=system_role_instruction,
            custom_resolution_prompt=custom_resolution_prompt
        )

        try:
            raw_text = self.llm_provider.generate(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                model=model,
                options={'temperature': 0}
            )
            reasoning, propositions = self.parse_propositions(raw_text)
            return reasoning, propositions, raw_text.strip()
        except Exception as e:
            logger.error(f"Erreur de résolution LLM : {e}")
            return None, [], f"Erreur lors de la génération des recommandations : {e}"

    def resolve_stream(
        self,
        query: str,
        historical_context: str,
        documentary_context: str,
        combined_context: str,
        num_propositions: int = 3,
        system_role_instruction: Optional[str] = None,
        custom_resolution_prompt: Optional[str] = None,
        model: Optional[str] = None
    ) -> Generator[str, None, None]:
        """Génération en mode stream renvoyant les chunks textuels."""
        if not self.llm_provider:
            yield "Aucun provider LLM configuré pour le streaming."
            return

        system_prompt, user_prompt = self.build_prompts(
            query=query,
            historical_context=historical_context,
            documentary_context=documentary_context,
            combined_context=combined_context,
            num_propositions=num_propositions,
            system_role_instruction=system_role_instruction,
            custom_resolution_prompt=custom_resolution_prompt
        )

        try:
            for chunk in self.llm_provider.generate_stream(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                model=model,
                options={'temperature': 0}
            ):
                if chunk:
                    yield chunk
        except Exception as e:
            logger.error(f"Erreur stream résolution LLM : {e}")
            yield f"Erreur de streaming : {e}"
