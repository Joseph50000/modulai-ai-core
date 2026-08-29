import logging
import json
import requests
import os
import time
from typing import Dict, Any, List, Optional
from src.providers.ollama_provider import OllamaProvider
from src.rag.vector_store import GenericVectorStore
from src.config_resolver import ConfigurationResolver

logger = logging.getLogger(__name__)

NODE_GATEWAY_URL = os.getenv("NODE_GATEWAY_URL", "http://localhost:3000/api")

class Orchestrator:
    def __init__(self):
        self.provider = OllamaProvider()
        # Cache des instances de VectorStore par collection
        self.vector_stores = {}
        self.config_resolver = ConfigurationResolver(NODE_GATEWAY_URL)

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

    def execute(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """
        Point d'entrée générique pour exécuter un Use Case IA.
        
        Payload attendu depuis le client Frontend :
        {
            "module": "gpr",
            "use_case": "analyse-plainte",
            "user_prompt": "Plainte: ...",
            "rag_config": {
                "enabled": true,
                "collection": "gpr_claims",
                "query": "texte de la plainte",
                "top_k": 3
            },
            "model_options": { "temperature": 0.2 }
        }
        """
        module = payload.get("module")
        use_case = payload.get("use_case")
        
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
        system_prompt = prompt_config.get("instructions") or self._fetch_prompt_config(module, use_case)
        if not system_prompt:
            return {"status": "error", "message": f"Configuration introuvable pour {module}/{use_case} dans ModulAI.", "resolved_configuration": snapshot}

        user_prompt = payload.get("user_prompt") or ""
        rag_config = snapshot.get("rag") or {}
        
        context_text = ""
        # 2. RAG (Retrieval Augmented Generation) si activé
        if rag_config.get("enabled"):
            collection = rag_config.get("collection")
            query = rag_config.get("query", user_prompt)
            top_k = rag_config.get("top_k", 3)
            
            if collection:
                store = self.get_vector_store(collection)
                results = store.search(query, top_k=top_k)
                if results:
                    context_lines = []
                    for i, r in enumerate(results):
                        context_lines.append(f"- Contexte {i+1} : {r['document']}")
                    context_text = "\n".join(context_lines)
                else:
                    context_text = "Aucun contexte trouvé dans la base de connaissances."
                    
        # 3. Construction du Prompt Final
        if "{context}" in system_prompt or "{{context}}" in system_prompt:
            system_prompt = system_prompt.replace("{context}", context_text).replace("{{context}}", context_text)
        elif context_text:
            system_prompt += f"\n\nContexte additionnel depuis la base de connaissances:\n{context_text}"
            
        # 3.5. Remplacement des variables personnalisées ({{variable}}) depuis le payload
        variables = payload.get("variables", {})
        if isinstance(variables, dict):
            for k, v in variables.items():
                system_prompt = system_prompt.replace(f"{{{{{k}}}}}", str(v))
                system_prompt = system_prompt.replace(f"{{{k}}}", str(v))
            
        # 3.8. Forcer le format de sortie JSON si un schéma est défini
        output_schema = payload.get("output_schema")
        model_options = payload.get("model_options") or {}
        
        if output_schema:
            schema_instructions = "\n\nCRITICAL INSTRUCTION: You MUST return your answer in raw JSON format matching this EXACT schema. Do NOT wrap the JSON in markdown code blocks. Just the raw JSON object.\nSchema:\n{"
            for field in output_schema:
                fname = field.get("name")
                ftype = field.get("type")
                fdesc = field.get("description")
                schema_instructions += f'\n  "{fname}": "{ftype} // {fdesc}",'
            schema_instructions += "\n}"
            
            system_prompt += schema_instructions
            model_options["format"] = "json"

        # 4. Utilisation des éléments déjà résolus par la hiérarchie du Core.
        provider_config = resolved.get("provider") or {}
        model_config = resolved.get("model") or {}
        policy = resolved.get("policy") or {}
        target_model = model_config.get("model_id") if model_config else None
        if provider_config:
            base_url = provider_config.get("endpoint_url") or provider_config.get("base_url")
            api_key = provider_config.get("api_key") or provider_config.get("secret_hash")
            self.provider = OllamaProvider(base_url=base_url, api_key=api_key, default_model=target_model)
        else:
            self.provider = OllamaProvider(default_model=target_model)
        if snapshot.get("temperature") is not None:
            model_options["temperature"] = snapshot["temperature"]
        if snapshot.get("token_limit") is not None:
            model_options.setdefault("num_predict", snapshot["token_limit"])

        # 5. Exécution LLM via le Provider dynamique
        start_time = time.time()
        try:
            result_text = self.provider.generate(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                options=model_options
            )
            execution_time_ms = int((time.time() - start_time) * 1000)
            status = "success"
            error_msg = ""
        except Exception as e:
            result_text = ""
            execution_time_ms = int((time.time() - start_time) * 1000)
            status = "error"
            error_msg = str(e)
            logger.error(f"Erreur de génération LLM: {e}")

        # 6. Enregistrement d'Audit
        try:
            audit_payload = {
                "project_id": payload.get("project_id"),
                "project_name": payload.get("project_name"),
                "module_name": module,
                "use_case": use_case,
                "prompt_name": use_case,
                "provider": provider_config.get("name") if provider_config else "default",
                "model": target_model or "default",
                "status": status,
                "execution_time": execution_time_ms,
                "user_name": "API User",
                "output": result_text if status == "success" else "",
                "error": error_msg,
                "human_validation": "required" if status == "success" and snapshot.get("human_validation_required") else ("pending" if status == "success" else "none"),
                "justification": "Validation humaine requise par la policy" if status == "success" and snapshot.get("human_validation_required") else ("En attente de justification humaine" if status == "success" else ""),
                "resources_used": json.dumps({"prompt_chars": len(system_prompt), "provider": provider_config.get("name") or "default", "rag": bool(context_text)}, ensure_ascii=False),
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
                "message": error_msg,
                "resolved_configuration": snapshot
            }
            
        return {
            "status": "success",
            "module": module,
            "use_case": use_case,
            "result": result_text,
            "rag_context_used": bool(context_text),
            "resolved_configuration": snapshot
        }
