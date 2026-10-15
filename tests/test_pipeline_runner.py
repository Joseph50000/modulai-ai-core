import json
import unittest
from unittest.mock import MagicMock

from src.pipeline_runner import PipelineRunner


class DummyPipelineLlmProvider:
    def __init__(self, responses: dict):
        # responses map step signature or sequence
        self.responses = responses
        self.call_history = []

    def generate(self, system_prompt: str, user_prompt: str, options: dict = None) -> str:
        self.call_history.append({
            "system_prompt": system_prompt,
            "user_prompt": user_prompt,
            "options": options,
        })
        # Trouver la réponse correspondante
        for key, resp in self.responses.items():
            if key in system_prompt:
                return resp
        # Défaut
        return json.dumps({"status": "default_response"})


class TestPipelineRunner(unittest.TestCase):
    """
    Tests unitaires pour le moteur de Pipeline de Prompts (Prompt Chaining) de ModulAI.
    """

    def test_two_step_pipeline_with_variable_interpolation(self):
        """Vérifie qu'un pipeline à 2 étapes interpole bien les sorties de l'étape 1 dans l'étape 2."""
        provider = DummyPipelineLlmProvider({
            "EVALUATION_STEP": json.dumps({
                "sentiment": "negatif",
                "urgence": "GRAVE",
                "contentieux": True,
            }),
            "QUALIFICATION_STEP": json.dumps({
                "categorie": "LITIGE_FRAUDE",
                "motif": "RETRAIT_DAB_CONTESTE",
            }),
        })

        runner = PipelineRunner(default_provider=provider)

        payload = {
            "output_strategy": "merge_all",
            "input": {
                "texte": "Mon argent a été débité hier au DAB sans mon accord !"
            },
            "steps": [
                {
                    "id": "step_1",
                    "name": "Évaluation",
                    "system_prompt": "EVALUATION_STEP: Analyse le texte : {{input.texte}}",
                    "output_schema": [
                        {"name": "sentiment", "type": "string"},
                        {"name": "urgence", "type": "string"},
                        {"name": "contentieux", "type": "boolean"},
                    ],
                },
                {
                    "id": "step_2",
                    "name": "Qualification",
                    "system_prompt": "QUALIFICATION_STEP: Sachant que l'urgence est {{steps.step_1.urgence}} et contentieux={{steps.step_1.contentieux}}, qualifie le dossier.",
                    "output_schema": [
                        {"name": "categorie", "type": "string"},
                        {"name": "motif", "type": "string"},
                    ],
                },
            ],
        }

        result = runner.run(payload)

        self.assertEqual(result["status"], "success")
        parsed = result["parsed_result"]
        # Vérification du résultat fusionné (merge_all)
        self.assertEqual(parsed["urgence"], "GRAVE")
        self.assertEqual(parsed["sentiment"], "negatif")
        self.assertEqual(parsed["categorie"], "LITIGE_FRAUDE")
        self.assertEqual(parsed["motif"], "RETRAIT_DAB_CONTESTE")

        # Vérification que le prompt de l'étape 2 a bien reçu les variables interpolées
        step2_call = provider.call_history[1]
        self.assertIn("l'urgence est GRAVE", step2_call["system_prompt"])
        self.assertIn("contentieux=true", step2_call["system_prompt"])

        # Vérification des métriques de pipeline
        metrics = result["pipeline_metrics"]
        self.assertEqual(metrics["total_steps"], 2)
        self.assertEqual(metrics["executed_steps"], 2)

    def test_pipeline_with_rag_on_specific_step(self):
        """Vérifie qu'un RAG peut être activé uniquement sur une étape spécifique du pipeline."""
        mock_store = MagicMock()
        mock_store.search.return_value = [
            {"document": "Règlement 102 : En cas de fraude DAB avérée, procédure sous 48h.", "similarity_score": 0.95}
        ]

        provider = DummyPipelineLlmProvider({
            "STEP_1": json.dumps({"urgence": "GRAVE"}),
            "STEP_2": json.dumps({"resolution": "Appliquer règlement 102"}),
        })

        runner = PipelineRunner(
            default_provider=provider,
            vector_store_resolver=lambda name: mock_store,
        )

        payload = {
            "input": {"dossier_id": "D-99"},
            "steps": [
                {
                    "id": "s1",
                    "system_prompt": "STEP_1",
                    "output_schema": [{"name": "urgence", "type": "string"}],
                },
                {
                    "id": "s2",
                    "system_prompt": "STEP_2: Contexte réglementaire : {context}",
                    "rag_config": {
                        "enabled": True,
                        "collection": "reglements_banque",
                        "query": "fraude dab",
                    },
                    "output_schema": [{"name": "resolution", "type": "string"}],
                },
            ],
        }

        result = runner.run(payload)
        self.assertEqual(result["status"], "success")

        # Vérifier que le vector store a été interrogé pour s2
        mock_store.search.assert_called_once()
        step2_call = provider.call_history[1]
        self.assertIn("Règlement 102", step2_call["system_prompt"])

    def test_pipeline_fallback_synthesis(self):
        """Vérifie que la synthèse de fallback fonctionne si le provider LLM n'est pas disponible."""
        runner = PipelineRunner(default_provider=None)

        payload = {
            "steps": [
                {
                    "id": "step_test",
                    "output_schema": [
                        {"name": "score", "type": "number"},
                        {"name": "valide", "type": "boolean"},
                        {"name": "tags", "type": "array"},
                    ],
                }
            ]
        }

        result = runner.run(payload)
        self.assertEqual(result["status"], "success")
        parsed = result["parsed_result"]
        self.assertEqual(parsed["score"], 0)
        self.assertEqual(parsed["valide"], False)
        self.assertEqual(parsed["tags"], [])


if __name__ == "__main__":
    unittest.main()
