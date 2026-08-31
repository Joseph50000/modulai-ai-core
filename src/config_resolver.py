import json
import logging
from typing import Any, Dict, List, Optional

import requests

logger = logging.getLogger(__name__)


class ConfigurationResolver:
    """Résout une configuration immuable et auditable pour une exécution AI."""

    def __init__(self, gateway_url: str, timeout: int = 5):
        self.gateway_url = gateway_url.rstrip('/')
        self.timeout = timeout

    def _get(self, resource: str, params: Optional[Dict[str, Any]] = None) -> Any:
        try:
            response = requests.get(f"{self.gateway_url}/{resource}", params=params or {}, timeout=self.timeout)
            if response.ok:
                return response.json()
        except Exception as error:
            logger.warning("Configuration fetch failed for %s: %s", resource, error)
        return []

    @staticmethod
    def _json(value: Any, fallback: Any) -> Any:
        if isinstance(value, (dict, list)):
            return value
        if not value:
            return fallback
        try:
            return json.loads(value)
        except (TypeError, ValueError):
            return fallback

    @staticmethod
    def _first(items: List[Dict[str, Any]], predicate) -> Optional[Dict[str, Any]]:
        for item in items or []:
            if predicate(item):
                return item
        return None

    def resolve(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        project_id = payload.get("project_id")
        module_id = payload.get("module_id")
        module_key = payload.get("module")
        use_case = payload.get("use_case") or ""

        settings_list = self._get("coresettings", {"limit": 1})
        settings = settings_list[0] if isinstance(settings_list, list) and settings_list else {}
        project = self._get(f"project/{project_id}") if project_id else {}
        module = self._get(f"module/{module_id}") if module_id else {}
        if not module and module_key:
            modules = self._get("module", {"module_key": module_key, "limit": 20})
            module = self._first(modules, lambda item: item.get("module_key") == module_key) or {}

        providers = self._get("aiprovider", {"status": "active", "limit": 100})
        models = self._get("aimodel", {"status": "active", "limit": 100})
        prompts = self._get("prompt", {"status": "active", "limit": 100})
        policies = self._get("aipolicy", {"status": "active", "limit": 100})
        versions = self._get("coreversion", {"status": "active", "limit": 20})
        knowledge_bases = self._get("knowledgebase", {"limit": 200})
        # `ready` est l’état opérationnel d’une base indexée ; `active` reste accepté pour les configurations legacy.
        knowledge_bases = [kb for kb in (knowledge_bases or []) if kb.get("status") in {"active", "ready"}]

        project_config_raw = self._json(project.get("configuration"), {})
        project_core_config = project_config_raw.get("core") if isinstance(project_config_raw.get("core"), dict) else {}
        # Le frontend stocke les overrides projet dans configuration.core ; les valeurs
        # legacy au niveau racine restent acceptées pour compatibilité.
        project_config = {**project_config_raw, **project_core_config}
        module_config = self._json(module.get("configuration"), {})
        payload_config = payload.get("configuration") if isinstance(payload.get("configuration"), dict) else {}

        def matches_scope(policy: Dict[str, Any], scope: str, ref: Optional[str]) -> bool:
            return policy.get("scope") == scope and (not ref or policy.get("scope_ref") in {ref, use_case, module_id, project_id})

        policy = (
            self._first(policies, lambda item: matches_scope(item, "use_case", use_case))
            or self._first(policies, lambda item: matches_scope(item, "module", module_id or module_key))
            or self._first(policies, lambda item: matches_scope(item, "project", project_id))
            or self._first(policies, lambda item: item.get("scope") in {"global", "core", None})
        )

        prompt = (
            self._first(prompts, lambda item: item.get("use_case") == use_case and item.get("module_id") == module_id)
            or self._first(prompts, lambda item: item.get("use_case") == f"{module_key}:{use_case}")
            or self._first(prompts, lambda item: item.get("use_case") == use_case and item.get("project_id") == project_id)
            or self._first(prompts, lambda item: item.get("use_case") == use_case)
        )

        requested_model_id = payload.get("model_options", {}).get("model") if isinstance(payload.get("model_options"), dict) else None
        configured_model_id = (
            requested_model_id
            or module_config.get("model_id")
            or module_config.get("model")
            or project_config.get("default_model_id")
            or project_config.get("model_id")
            or project_config.get("model")
            or payload_config.get("model_id")
            or payload_config.get("model")
            or settings.get("default_model_id")
        )
        model = self._first(models, lambda item: item.get("id") == configured_model_id or item.get("model_id") == configured_model_id)
        if not model and configured_model_id:
            model = self._get(f"aimodel/{configured_model_id}") or {}
        if not model:
            model = self._first(models, lambda item: item.get("is_default") is True) or (models[0] if models else {})

        explicit_provider_id = (
            module_config.get("provider_id")
            or project_config.get("default_provider")
            or project_config.get("provider_id")
            or module_config.get("provider")
            or project_config.get("provider")
            or payload_config.get("provider_id")
            or payload_config.get("provider")
        )
        # Un modèle appartient à un provider : lorsqu’un modèle est sélectionné,
        # son provider lié est prioritaire sur un ancien provider textuel conservé
        # dans une configuration legacy de module.
        configured_provider_id = (model or {}).get("provider_id") or explicit_provider_id or settings.get("default_provider")
        provider = self._first(providers, lambda item: item.get("id") == configured_provider_id or item.get("name") == configured_provider_id or item.get("type") == configured_provider_id)
        if not provider and configured_provider_id:
            provider = self._get(f"aiprovider/{configured_provider_id}") or {}
        if not provider:
            provider = self._first(providers, lambda item: item.get("is_default") is True) or (providers[0] if providers else {})

        current_version = settings.get("current_core_version")
        version = self._first(versions, lambda item: item.get("version") == current_version) or self._first(versions, lambda item: item.get("is_latest") is True) or {}
        model_options = payload.get("model_options") if isinstance(payload.get("model_options"), dict) else {}
        requested_rag = payload.get("rag_config") if isinstance(payload.get("rag_config"), dict) else {}
        rag_config = {
            "enabled": requested_rag.get("enabled", module_config.get("rag_enabled", project_config.get("rag_enabled", False))),
            "collection": requested_rag.get("collection") or module_config.get("knowledge_base_collection") or module_config.get("knowledge_base_id") or project_config.get("knowledge_base_collection") or project_config.get("knowledge_base_id"),
            "query": requested_rag.get("query"),
            "top_k": requested_rag.get("top_k", settings.get("rag_top_k", 3)),
            **requested_rag,
        }
        requested_kb_id = payload.get("knowledge_base_id") or payload.get("knowledgeBaseId") or rag_config.get("knowledge_base_id") or rag_config.get("knowledgeBaseId")
        requested_collection = rag_config.get("collection")
        selected_kb = self._first(knowledge_bases, lambda item: item.get("id") == requested_kb_id or item.get("id") == requested_collection or f"kb_{item.get('id')}" == requested_collection)
        allowed_kb = bool(selected_kb) and ((not selected_kb.get("project_id") and not selected_kb.get("module_id")) or selected_kb.get("project_id") == project_id or selected_kb.get("module_id") in {module_id, module_key})
        violations = []
        if policy and policy.get("rag_required") and not rag_config.get("enabled"):
            violations.append("Cette policy exige l’utilisation d’une base de connaissances RAG.")
        if rag_config.get("enabled") and (requested_kb_id or requested_collection) and not allowed_kb:
            violations.append("La base de connaissances demandée n’est pas accessible dans la portée de cette exécution.")

        temperature = model_options.get("temperature")
        if temperature is None:
            temperature = model.get("temperature") or settings.get("default_temperature")
        if policy and policy.get("temperature_max") is not None and temperature is not None:
            temperature = min(float(temperature), float(policy["temperature_max"]))

        allowed_models = self._json(policy.get("allowed_models"), []) if policy else []
        if allowed_models and (model.get("id") not in allowed_models and model.get("model_id") not in allowed_models):
            fallback_id = policy.get("fallback_model_id")
            fallback = self._first(models, lambda item: item.get("id") == fallback_id or item.get("model_id") == fallback_id)
            if fallback:
                model = fallback

        snapshot = {
            "project_id": project_id,
            "module_id": module_id or module.get("id"),
            "module_key": module_key or module.get("module_key"),
            "use_case": use_case,
            "provider_id": provider.get("id") if provider else None,
            "provider_name": provider.get("name") if provider else None,
            "model_id": model.get("id") if model else None,
            "model_key": model.get("model_id") if model else None,
            "prompt_id": prompt.get("id") if prompt else None,
            "prompt_version": prompt.get("version") if prompt else None,
            "policy_id": policy.get("id") if policy else None,
            "policy_name": policy.get("name") if policy else None,
            "core_version": version.get("version") or current_version,
            "temperature": temperature,
            "token_limit": module_config.get("max_tokens") or project_config.get("max_tokens") or model.get("max_tokens") or settings.get("default_token_limit"),
            "rag": rag_config,
            "knowledge_base_ids": payload.get("knowledge_base_ids") or rag_config.get("knowledge_base_ids") or ([selected_kb.get("id")] if selected_kb else []),
            "knowledge_base_id": selected_kb.get("id") if selected_kb else requested_kb_id,
            "knowledge_base_scope_allowed": allowed_kb if (requested_kb_id or requested_collection) else True,
            "human_validation_required": bool(policy.get("human_validation_required")) if policy else False,
            "policy_violations": violations,
        }
        return {
            "settings": settings,
            "project": project,
            "module": module,
            "provider": provider or {},
            "model": model or {},
            "prompt": prompt or {},
            "policy": policy or {},
            "version": version or {},
            "knowledge_base": selected_kb or {},
            "snapshot": snapshot,
        }
