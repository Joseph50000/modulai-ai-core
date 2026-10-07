import unittest

from main import ExecutePayload
from src.config_resolver import ConfigurationResolver


class FixtureResolver(ConfigurationResolver):
    def __init__(self):
        super().__init__("http://gateway.test")
        self.resources = {
            "coresettings": [{
                "default_model_id": "model-default",
                "default_provider": "provider-default",
                "default_temperature": 0.2,
                "default_token_limit": 1024,
            }],
            "project/project-1": {
                "id": "project-1",
                "configuration": "{}",
            },
            "module/module-1": {
                "id": "module-1",
                "module_key": "gpr",
                "configuration": "{}",
            },
            "aiprovider": [{
                "id": "provider-default",
                "name": "Test provider",
                "status": "active",
            }],
            "aimodel": [{
                "id": "model-default",
                "model_id": "test-model",
                "provider_id": "provider-default",
                "status": "active",
                "temperature": 0.2,
            }],
            "prompt": [{
                "id": "prompt-1",
                "use_case": "analyse-plainte",
                "module_id": "module-1",
                "version": "1.0.0",
                "instructions": "Analyse : {{complaint}}",
                "status": "active",
            }],
            "aipolicy": [],
            "coreversion": [],
            "knowledgebase": [],
        }

    def _get(self, resource, params=None):
        return self.resources.get(resource, [])


class ConfigurationContractTests(unittest.TestCase):
    def test_canonical_payload_is_accepted(self):
        payload = ExecutePayload(
            project_id="project-1",
            module_id="module-1",
            module_key="gpr",
            use_case_key="analyse-plainte",
            input={"complaint": "Texte de test"},
            request_options={"rag_query": "Texte de test", "top_k": 3},
        )

        self.assertEqual(payload.module_key, "gpr")
        self.assertEqual(payload.use_case_key, "analyse-plainte")
        self.assertEqual(payload.input["complaint"], "Texte de test")
        self.assertEqual(payload.request_options["top_k"], 3)

    def test_resolver_uses_canonical_identifiers_and_options(self):
        resolver = FixtureResolver()
        result = resolver.resolve({
            "project_id": "project-1",
            "module_id": "module-1",
            "module_key": "gpr",
            "use_case_key": "analyse-plainte",
            "input": {"complaint": "Texte de test"},
            "request_options": {"rag_query": "Texte de test", "top_k": 3},
        })

        snapshot = result["snapshot"]
        self.assertEqual(snapshot["module_id"], "module-1")
        self.assertEqual(snapshot["module_key"], "gpr")
        self.assertEqual(snapshot["use_case_key"], "analyse-plainte")
        self.assertEqual(snapshot["prompt_id"], "prompt-1")
        self.assertEqual(snapshot["model_id"], "model-default")
        self.assertEqual(snapshot["rag"]["query"], "Texte de test")
        self.assertEqual(snapshot["rag"]["top_k"], 3)
        self.assertEqual(snapshot["policy_violations"], [])

    def test_legacy_payload_remains_supported(self):
        resolver = FixtureResolver()
        result = resolver.resolve({
            "project_id": "project-1",
            "module": "gpr",
            "use_case": "analyse-plainte",
            "variables": {"complaint": "Texte legacy"},
            "model_options": {},
            "rag_config": {},
        })

        self.assertEqual(result["snapshot"]["module_key"], "gpr")
        self.assertEqual(result["snapshot"]["use_case_key"], "analyse-plainte")
        self.assertEqual(result["snapshot"]["prompt_id"], "prompt-1")


if __name__ == "__main__":
    unittest.main()
