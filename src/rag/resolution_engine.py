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

    def _generate_fallback_propositions(
        self,
        query: str,
        historical_context: str,
        documentary_context: str,
        num_propositions: int = 3
    ) -> List[PropositionItem]:
        """Génère des propositions structurées agnostiques à partir du contexte RAG quand le LLM est indisponible."""
        propositions: List[PropositionItem] = []
        extracted_actions = []

        # 1. Extraction depuis l'historique (lignes "Solution/Action retenue :" ou "Solution:")
        if historical_context and "Aucun cas historique" not in historical_context:
            sol_matches = re.findall(r"(?:Solution(?:/Action retenue)?\s*:\s*)([^\n\r]+)", historical_context, re.IGNORECASE)
            for sol in sol_matches:
                cleaned = sol.strip()
                if cleaned and len(cleaned) > 5 and cleaned not in [a[0] for a in extracted_actions]:
                    extracted_actions.append((cleaned, "Basé sur les résolutions similaires de l'historique opérationnel"))

        # 2. Extraction depuis les références documentaires
        if documentary_context and "Aucune documentation" not in documentary_context:
            doc_lines = [l.strip() for l in documentary_context.splitlines() if l.strip().startswith("- Référence")]
            for dl in doc_lines:
                title_match = re.search(r"\[(.*?)\]", dl)
                if title_match:
                    ref_title = title_match.group(1).strip()
                    action = f"Application de la procédure de référence : {ref_title}"
                    if action not in [a[0] for a in extracted_actions]:
                        extracted_actions.append((action, "Conforme aux directives documentaires et réglementaires en vigueur"))

        # 3. Repli général sur les cas indexés si aucun motif strict n'a matché
        if not extracted_actions and historical_context and "Aucun cas historique" not in historical_context:
            for line in historical_context.splitlines():
                if line.strip().startswith("- Cas"):
                    extracted_actions.append((line.strip().lstrip("- "), "Cas similaire référencé dans la base"))

        for i, item in enumerate(extracted_actions[:num_propositions]):
            title, details = item
            propositions.append(PropositionItem(index=i + 1, title=title, details=details))

        return propositions

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
            # Mode hors-ligne direct
            fallback_props = self._generate_fallback_propositions(
                query=query,
                historical_context=historical_context,
                documentary_context=documentary_context,
                num_propositions=num_propositions
            )
            if fallback_props:
                reasoning = "Analyse synthétisée à partir des sources indexées (aucun provider LLM connecté)."
                raw = f"RAISONNEMENT : {reasoning}\n\n" + "\n".join([f"{p.index}. {p.title} | {p.details}" for p in fallback_props])
                return reasoning, fallback_props, raw
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
            logger.warning(f"Erreur de résolution LLM ({e}), bascule sur la synthèse contextuelle hors-ligne.")
            fallback_props = self._generate_fallback_propositions(
                query=query,
                historical_context=historical_context,
                documentary_context=documentary_context,
                num_propositions=num_propositions
            )
            if fallback_props:
                fallback_reasoning = (
                    "Analyse synthétisée à partir des sources documentaires et des cas historiques indexés "
                    f"(Mode résilient hors-ligne suite à indisponibilité du LLM)."
                )
                raw_msg = (
                    f"RAISONNEMENT : {fallback_reasoning}\n\n"
                    + "\n".join([f"{p.index}. {p.title} | {p.details}" for p in fallback_props])
                )
                return fallback_reasoning, fallback_props, raw_msg

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
            fallback_props = self._generate_fallback_propositions(
                query=query,
                historical_context=historical_context,
                documentary_context=documentary_context,
                num_propositions=num_propositions
            )
            if fallback_props:
                yield "RAISONNEMENT : Analyse synthétisée à partir des sources indexées (mode hors-ligne).\n\n"
                for p in fallback_props:
                    yield f"{p.index}. {p.title} | {p.details}\n"
            else:
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
            logger.warning(f"Erreur stream résolution LLM ({e}), bascule sur la synthèse contextuelle hors-ligne.")
            fallback_props = self._generate_fallback_propositions(
                query=query,
                historical_context=historical_context,
                documentary_context=documentary_context,
                num_propositions=num_propositions
            )
            if fallback_props:
                yield "RAISONNEMENT : Analyse synthétisée à partir des sources documentaires et des cas historiques indexés (Mode résilient hors-ligne).\n\n"
                for p in fallback_props:
                    yield f"{p.index}. {p.title} | {p.details}\n"
            else:
                yield f"Erreur de streaming : {e}"
