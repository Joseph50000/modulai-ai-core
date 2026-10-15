import logging
import json
import requests
import os
import time
from typing import Dict, Any, List, Optional
from src.providers.ollama_provider import OllamaProvider
from src.providers.openai_provider import OpenAICompatibleProvider
from src.rag.vector_store import GenericVectorStore
from src.config_resolver import ConfigurationResolver
from src.pipeline_runner import PipelineRunner

logger = logging.getLogger(__name__)

NODE_GATEWAY_URL = os.getenv("NODE_GATEWAY_URL", "http://localhost:3000/api")

class Orchestrator:
    def __init__(self):
        cloud_key = os.getenv("GROQ_API_KEY") or os.getenv("LLM_API_KEY")
        if cloud_key:
            self.provider = OpenAICompatibleProvider(
                base_url=os.getenv("LLM_BASE_URL", "https://api.groq.com/openai/v1"),
                api_key=cloud_key,
                default_model=os.getenv("LLM_MODEL_NAME", "qwen/qwen3.8-27b"),
                name="Groq Cloud"
            )
        else:
            self.provider = OllamaProvider()
        # Cache des instances de VectorStore par collection
        self.vector_stores = {}
        self.config_resolver = ConfigurationResolver(NODE_GATEWAY_URL)
        self.pipeline_runner = PipelineRunner(
            provider_resolver=lambda: self.provider,
            vector_store_resolver=self.get_vector_store,
            default_provider=self.provider,
        )

    def get_vector_store(self, collection_name: str) -> GenericVectorStore:
        if collection_name not in self.vector_stores:
            self.vector_stores[collection_name] = GenericVectorStore(collection_name=collection_name)
        return self.vector_stores[collection_name]

    def _fetch_active_provider(self) -> Optional[Dict[str, Any]]:
        """
        Récupère dynamiquement le provider actif depuis la base de données (Node Gateway)
        """
        try:
            response = requests.get(
                f"{NODE_GATEWAY_URL}/aiprovider",
                params={"status": "active", "limit": 1},
                timeout=5
            )
            if response.status_code == 200:
                providers = response.json()
                if providers and len(providers) > 0:
                    return providers[0]
            return None
        except Exception as e:
            logger.error(f"Erreur lors de la récupération du provider: {e}")
            return None

    def _fetch_default_model(self) -> Optional[Dict[str, Any]]:
        """
        Récupère dynamiquement le modèle par défaut depuis la base de données (Node Gateway)
        """
        try:
            settings_res = requests.get(f"{NODE_GATEWAY_URL}/coresettings", timeout=5)
            if settings_res.status_code == 200 and settings_res.json():
                settings = settings_res.json()[0]
                model_id = settings.get("default_model_id")
                if model_id:
                    model_res = requests.get(f"{NODE_GATEWAY_URL}/aimodel/{model_id}", timeout=5)
                    if model_res.status_code == 200:
                        return model_res.json()
            return None
        except Exception as e:
            logger.error(f"Erreur lors de la récupération du modèle par défaut: {e}")
            return None

    def _fetch_active_policy(self, scope: str = "global") -> Optional[Dict[str, Any]]:
        """
        Récupère dynamiquement la politique de sécurité (Policy) active depuis la BDD.
        """
        try:
            res = requests.get(
                f"{NODE_GATEWAY_URL}/aipolicy",
                params={"status": "active", "scope": scope, "limit": 1},
                timeout=5
            )
            if res.status_code == 200 and res.json():
                return res.json()[0]
            return None
        except Exception as e:
            logger.error(f"Erreur lors de la récupération de la policy: {e}")
            return None

    def _fetch_prompt_config(self, module: str, use_case: str) -> str:
        """
        Récupère dynamiquement les instructions du prompt depuis la base de données (Node Gateway)
        """
        try:
            # Appel à l'API Node.js pour chercher tous les prompts actifs
            response = requests.get(
                f"{NODE_GATEWAY_URL}/prompt",
                params={"status": "active"},
                timeout=5
            )
            response.raise_for_status()
            
            prompts = response.json()
            # On cherche d'abord la clé composite (créée via AI Core), sinon la clé simple (créée via Module Registry)
            target_composite = f"{module}:{use_case}"
            
            for p in prompts:
                uc = p.get("use_case", "")
                if uc == target_composite or uc == use_case:
                    return p.get("instructions", "")
            
            logger.warning(f"Aucun prompt actif configuré en BDD pour use_case={target_composite} ou {use_case}")
            return ""
        except Exception as e:
            logger.error(f"Erreur lors de la récupération du prompt depuis le Gateway: {e}")
            return ""

    def resolve_provider_for_request(self, payload: Dict[str, Any], resolved: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Résout dynamiquement le provider, le modèle et la configuration associés à la requête.
        Retourne une instance OllamaProvider configurée et les métadonnées résolues.
        Réutilise l'objet resolved pré-calculé si fourni pour éviter tout appel réseau redondant.
        """
        if resolved is None:
            try:
                resolved = self.config_resolver.resolve(payload)
            except Exception as e:
                logger.warning(f"Erreur lors de la résolution de configuration : {e}")
                resolved = {}

        provider_config = resolved.get("provider") or {}
        model_config = resolved.get("model") or {}
        snapshot = resolved.get("snapshot") or {}

        settings = resolved.get("settings") or {}

        # 1. Modèle cible dynamique (priorité : payload -> model_config -> settings DB -> env -> generic fallback)
        default_model_env = os.getenv("LLM_MODEL_NAME")
        raw_model = payload.get("model")
        if raw_model and model_config.get("name") == raw_model and model_config.get("model_id"):
            raw_model = model_config.get("model_id")

        target_model_id = (
            raw_model
            or model_config.get("model_id")
            or model_config.get("name")
            or settings.get("default_model_id")
            or settings.get("default_model_name")
            or default_model_env
            or "default"
        )
        model_display_name = (
            model_config.get("name")
            or settings.get("default_model_name")
            or payload.get("model")
            or target_model_id
        )

        # 2. Provider cible dynamique (priorité : payload -> model_options -> request_options -> provider_config -> settings DB -> generic fallback)
        model_opts = payload.get("model_options") if isinstance(payload.get("model_options"), dict) else {}
        req_opts = payload.get("request_options") if isinstance(payload.get("request_options"), dict) else {}

        # Cohérence modèle-provider : si le modèle appartient à un provider spécifique et qu'aucun provider n'est forcé
        model_prov_id = model_config.get("provider_id")
        if model_prov_id and not payload.get("provider") and not model_opts.get("provider") and not req_opts.get("provider"):
            if provider_config.get("id") != model_prov_id and provider_config.get("name") != model_prov_id:
                try:
                    res_p = requests.get(f"{NODE_GATEWAY_URL}/aiprovider/{model_prov_id}", timeout=3)
                    if res_p.status_code == 200 and res_p.json():
                        p_data = res_p.json()
                        provider_config = p_data[0] if isinstance(p_data, list) and p_data else p_data
                except Exception as e:
                    logger.warning(f"Impossible d'aligner le provider avec le modèle : {e}")

        provider_name = (
            payload.get("provider")
            or model_opts.get("provider")
            or req_opts.get("provider")
            or provider_config.get("name")
            or settings.get("default_provider")
            or "default"
        )
        base_url = (
            payload.get("endpoint_url")
            or model_opts.get("endpoint_url")
            or req_opts.get("endpoint_url")
            or provider_config.get("endpoint_url")
            or provider_config.get("base_url")
        )
        api_key = (
            payload.get("api_key")
            or model_opts.get("api_key")
            or req_opts.get("api_key")
            or provider_config.get("api_key")
            or provider_config.get("secret_hash")
        )

        provider_type = (provider_config.get("type") or "").lower()
        provider_name_lower = str(provider_name).lower()

        is_ollama = (
            "ollama" in provider_name_lower
            or "ollama" in provider_type
            or provider_type == "local"
            or (base_url and ("ollama" in str(base_url) or "11434" in str(base_url)))
        ) and not (
            "groq" in provider_name_lower
            or (base_url and "api.groq.com" in str(base_url))
            or (api_key and str(api_key).startswith("gsk_"))
        )

        is_openai_cloud = not is_ollama and (
            "groq" in provider_name_lower
            or "groq" in provider_type
            or "openai" in provider_name_lower
            or "openai" in provider_type
            or (base_url and any(h in str(base_url) for h in ["api.groq.com", "api.openai.com", "openrouter", "together"]))
            or (api_key and str(api_key).startswith("gsk_"))
        )

        if is_openai_cloud:
            provider_instance = OpenAICompatibleProvider(
                base_url=base_url or "https://api.groq.com/openai/v1",
                api_key=api_key or os.getenv("LLM_API_KEY") or "",
                default_model=target_model_id or "qwen/qwen3.8-27b",
                name=provider_name
            )
        else:
            provider_instance = OllamaProvider(
                base_url=base_url,
                api_key=api_key,
                default_model=target_model_id,
                name=provider_name
            )

        return {
            "provider_instance": provider_instance,
            "provider_name": provider_name,
            "model_id": target_model_id,
            "model_name": model_display_name,
            "snapshot": snapshot,
            "resolved": resolved
        }

    def execute(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """
        Point d'entrée générique pour exécuter un Use Case IA.
        
        Payload attendu depuis le client Frontend :
        {
            "module": "support",
            "use_case": "ticket-triage",
            "user_prompt": "Ticket: ...",
            "rag_config": {
                "enabled": true,
                "collection": "knowledge_base",
                "query": "texte de la requete",
                "top_k": 3
            },
            "model_options": { "temperature": 0.2 }
        }
        """
        module = payload.get("module_key") or payload.get("module")
        use_case = payload.get("use_case") or payload.get("use_case_key")
        input_data = payload.get("input") if isinstance(payload.get("input"), dict) else payload.get("variables", {})
        
        logger.info(f"Orchestration dynamique - Module: {module} | Use Case: {use_case}")
        
        # 1. Résolution unique et hiérarchique de toute la configuration du Core.
        resolved = self.config_resolver.resolve(payload)
        snapshot = resolved["snapshot"]
        if snapshot.get("policy_violations"):
            return {
                "status": "error",
                "module": module,
                "use_case": use_case,
                "message": "Exécution refusée par la policy: " + " ".join(snapshot["policy_violations"]),
                "resolved_configuration": snapshot,
            }
        prompt_config = resolved.get("prompt") or {}

        # 2. Résolution dynamique du Provider et du Modèle
        resolved_provider_ctx = self.resolve_provider_for_request(payload, resolved=resolved)
        self.provider = resolved_provider_ctx["provider_instance"]
        target_model = resolved_provider_ctx["model_id"]
        if target_model and hasattr(self.provider, "default_model"):
            self.provider.default_model = target_model

        # 3. Détection du mode Pipeline (Multi-step Prompt Chaining)
        steps = (
            payload.get("steps")
            or (payload.get("configuration") or {}).get("steps")
            or prompt_config.get("steps")
        )
        if steps:
            logger.info(f"Délégation de l'exécution au PipelineRunner ({len(steps)} étapes détectées)")
            pipeline_result = self.pipeline_runner.run(payload, resolved=resolved)
            pipeline_result["module"] = module
            pipeline_result["use_case"] = use_case
            pipeline_result["resolved_configuration"] = snapshot
            if "resources_used" not in pipeline_result:
                pipeline_result["resources_used"] = {
                    "total_steps": len(steps),
                    "provider": resolved_provider_ctx.get("provider_name") or "default",
                }
            return pipeline_result

        system_prompt = (
            payload.get("system_prompt_template")
            or payload.get("system_prompt")
            or payload.get("prompt")
            or prompt_config.get("instructions")
            or self._fetch_prompt_config(module, use_case)
        )
        if not system_prompt:
            return {"status": "error", "message": f"Configuration introuvable pour {module}/{use_case} dans ModulAI.", "resolved_configuration": snapshot}

        user_prompt = payload.get("user_prompt") or ""
        if not user_prompt and isinstance(input_data, dict):
            user_prompt = "\n".join(
                f"{key}: {json.dumps(value, ensure_ascii=False) if isinstance(value, (dict, list)) else value or ''}"
                for key, value in input_data.items()
            )
        rag_config = snapshot.get("rag") or {}
        
        context_text = ""
        historical_context_text = ""
        documentary_context_text = ""

        # 2. RAG (Retrieval Augmented Generation) si activé
        if rag_config.get("enabled"):
            query = rag_config.get("query") or user_prompt or ""
            min_score = rag_config.get("min_similarity_score")
            
            # Recherche historique / transactionnelle
            hist_col = rag_config.get("historical_collection") or rag_config.get("collection")
            if hist_col:
                top_k_hist = rag_config.get("top_k_history") or rag_config.get("top_k", 3)
                hist_filter = rag_config.get("history_filter") or rag_config.get("filter_metadata")
                store = self.get_vector_store(hist_col)
                hist_results = store.search(query, top_k=top_k_hist, filter_metadata=hist_filter, min_similarity_score=min_score)
                if hist_results:
                    context_lines = []
                    for i, r in enumerate(hist_results):
                        context_lines.append(f"- Cas similaire {i+1} : {r['document']}")
                    historical_context_text = "\n".join(context_lines)

            # Recherche documentaire / procédurale
            doc_col = rag_config.get("documentary_collection")
            if doc_col:
                top_k_doc = rag_config.get("top_k_docs") or 3
                doc_filter = rag_config.get("documentary_filter")
                doc_store = self.get_vector_store(doc_col)
                doc_results = doc_store.search(query, top_k=top_k_doc, filter_metadata=doc_filter, min_similarity_score=min_score)
                if doc_results:
                    doc_lines = []
                    for i, r in enumerate(doc_results):
                        doc_lines.append(f"- Référence {i+1} : {r['document']}")
                    documentary_context_text = "\n".join(doc_lines)

            # Combinaison pour rétrocompatibilité
            combined_parts = []
            if historical_context_text:
                combined_parts.append(historical_context_text)
            if documentary_context_text:
                combined_parts.append(documentary_context_text)
            context_text = "\n\n".join(combined_parts) if combined_parts else "Aucun contexte trouvé dans la base de connaissances."
                    
        # 3. Construction du Prompt Final avec injection multi-contextes
        if "{historical_context}" in system_prompt or "{{historical_context}}" in system_prompt:
            system_prompt = system_prompt.replace("{historical_context}", historical_context_text).replace("{{historical_context}}", historical_context_text)

        if "{documentary_context}" in system_prompt or "{{documentary_context}}" in system_prompt:
            system_prompt = system_prompt.replace("{documentary_context}", documentary_context_text).replace("{{documentary_context}}", documentary_context_text)

        if "{context}" in system_prompt or "{{context}}" in system_prompt:
            system_prompt = system_prompt.replace("{context}", context_text).replace("{{context}}", context_text)
        elif context_text and context_text != "Aucun contexte trouvé dans la base de connaissances.":
            system_prompt += f"\n\nContexte additionnel depuis la base de connaissances:\n{context_text}"
            
        # 3.5. Remplacement des variables personnalisées ({{variable}}) depuis le payload
        variables = input_data
        if isinstance(variables, dict):
            for k, v in variables.items():
                system_prompt = system_prompt.replace(f"{{{{{k}}}}}", str(v))
                system_prompt = system_prompt.replace(f"{{{k}}}", str(v))
            
        # 3.8. Forcer le format de sortie JSON si un schéma est défini
        output_schema = payload.get("output_schema")
        if isinstance(output_schema, str):
            try:
                output_schema = json.loads(output_schema)
            except Exception:
                pass

        model_options = payload.get("model_options") or {}
        
        if output_schema:
            schema_instructions = "\n\nCRITICAL INSTRUCTION: You MUST return your answer in raw JSON format matching this EXACT schema. Do NOT wrap the JSON in markdown code blocks. Just the raw JSON object.\nSchema:\n{"
            if isinstance(output_schema, list):
                for field in output_schema:
                    if isinstance(field, dict):
                        fname = field.get("name") or field.get("key") or "item"
                        ftype = field.get("type") or "string"
                        fdesc = field.get("description") or ""
                        schema_instructions += f'\n  "{fname}": "{ftype} // {fdesc}",'
            elif isinstance(output_schema, dict):
                for k, v in output_schema.items():
                    schema_instructions += f'\n  "{k}": "{v}",'
            schema_instructions += "\n}"
            
            system_prompt += schema_instructions
            model_options["format"] = "json"

        # 4. Paramètres d'exécution résolus par la hiérarchie du Core.
        provider_config = resolved.get("provider") or {}
        model_config = resolved.get("model") or {}
        policy = resolved.get("policy") or {}

        if snapshot.get("temperature") is not None:
            model_options["temperature"] = snapshot["temperature"]
        elif output_schema and "temperature" not in model_options:
            model_options["temperature"] = 0
        if snapshot.get("token_limit") is not None:
            model_options.setdefault("num_predict", snapshot["token_limit"])
            model_options.setdefault("max_tokens", snapshot["token_limit"])

        # 5. Exécution LLM via le Provider dynamique
        start_time = time.time()
        try:
            result_text = self.provider.generate(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                options=model_options
            )
            # Nettoyer les balises markdown ```json éventuelles pour garantir un JSON pur
            if result_text and output_schema:
                clean_text = result_text.strip()
                if clean_text.startswith("```json"):
                    clean_text = clean_text[7:]
                elif clean_text.startswith("```"):
                    clean_text = clean_text[3:]
                if clean_text.endswith("```"):
                    clean_text = clean_text[:-3]
                result_text = clean_text.strip()

            execution_time_ms = int((time.time() - start_time) * 1000)
            status = "success"
            error_msg = ""
        except Exception as e:
            provider_label = getattr(self.provider, "name", "LLM")
            logger.error(f"Erreur lors de l'appel au Provider {provider_label} : {e}")
            result_text = ""
            execution_time_ms = int((time.time() - start_time) * 1000)
            status = "error"
            error_msg = f"Erreur Provider {provider_label}: {str(e)}"

        # 6. Enregistrement d'Audit
        resources_dict = {
            "prompt_chars": len(system_prompt),
            "provider": provider_config.get("name") if provider_config else (resolved_provider_ctx.get("provider_name") or "default"),
            "rag": bool(context_text),
        }

        should_persist_audit = not payload.get("skip_audit_persistence") and not payload.get("delegate_audit")
        if should_persist_audit:
            try:
                audit_payload = {
                    "project_id": payload.get("project_id"),
                    "project_name": payload.get("project_name"),
                    "module_name": module,
                    "use_case": use_case,
                    "prompt_name": use_case,
                    "provider": provider_config.get("name") if provider_config else "default",
                    "model": model_config.get("name") or target_model or "default",
                    "status": status,
                    "execution_time": execution_time_ms,
                    "user_name": "API User",
                    "output": result_text if status == "success" else "",
                    "error": error_msg,
                    "human_validation": "required" if status == "success" and snapshot.get("human_validation_required") else ("pending" if status == "success" else "none"),
                    "justification": "Validation humaine requise par la policy" if status == "success" and snapshot.get("human_validation_required") else ("En attente de justification humaine" if status == "success" else ""),
                    "resources_used": json.dumps(resources_dict, ensure_ascii=False),
                    "configuration_snapshot": json.dumps(snapshot, ensure_ascii=False, sort_keys=True),
                    "input_reference": payload.get("input_reference"),
                    "context_reference": payload.get("context_reference")
                }
                requests.post(f"{NODE_GATEWAY_URL}/aiexecution", json=audit_payload, timeout=5)
            except Exception as e:
                logger.error(f"Impossible d'enregistrer l'audit d'exécution: {e}")

        if status == "error":
            return {
                "status": "error",
                "module": module,
                "use_case": use_case,
                "error": error_msg,
                "message": error_msg,
                "execution_time_ms": execution_time_ms,
                "resources_used": resources_dict,
                "resolved_configuration": snapshot
            }
            
        return {
            "status": "success",
            "module": module,
            "use_case": use_case,
            "result": result_text,
            "execution_time_ms": execution_time_ms,
            "rag_context_used": bool(context_text),
            "resources_used": resources_dict,
            "resolved_configuration": snapshot
        }
