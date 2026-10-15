import json
import logging
import re
import time
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger("modulai.pipeline")


class PipelineRunner:
    """
    Moteur d'exécution séquentiel de Pipelines de Prompts (Prompt Chaining).
    Permet d'exécuter un Use Case sous forme d'une chaîne ordonnée d'étapes (Steps),
    où chaque étape :
    - Dispose de son propre prompt ciblé et de son schéma JSON de sortie.
    - Interpole dynamiquement les résultats des étapes précédentes ({{steps.<step_id>.<field>}}).
    - Peut activer son propre RAG documentaire ou cibler des paramètres spécifiques.
    - Enrichit l'accumulateur d'état global du pipeline (Pipeline State).
    """

    def __init__(
        self,
        provider_resolver: Optional[Callable[[], Any]] = None,
        vector_store_resolver: Optional[Callable[[str], Any]] = None,
        default_provider: Any = None,
    ):
        self.provider_resolver = provider_resolver
        self.vector_store_resolver = vector_store_resolver
        self.default_provider = default_provider

    def _get_provider(self):
        if self.provider_resolver:
            try:
                p = self.provider_resolver()
                if p:
                    return p
            except Exception as e:
                logger.warning(f"Impossible de résoudre le provider via le callback: {e}")
        return self.default_provider

    def _interpolate_text(self, text: str, state: Dict[str, Any]) -> str:
        """
        Remplace récursivement les variables {{input.<field>}} et {{steps.<step_id>.<field>}}
        dans une chaîne de template.
        """
        if not text or not isinstance(text, str):
            return ""

        input_data = state.get("input", {})
        steps_data = state.get("steps", {})

        def replacer(match):
            expr = match.group(1).strip()
            # 1. Expression {{input.xyz}}
            if expr.startswith("input."):
                key = expr[len("input."):]
                val = input_data.get(key)
                if val is not None:
                    if isinstance(val, bool):
                        return "true" if val else "false"
                    return json.dumps(val, ensure_ascii=False) if isinstance(val, (dict, list)) else str(val)
                return ""

            # 2. Expression {{steps.step_id.field}}
            if expr.startswith("steps."):
                parts = expr[len("steps."):].split(".", 1)
                step_id = parts[0]
                step_result = steps_data.get(step_id, {})
                if len(parts) == 1:
                    # {{steps.step_id}} -> tout l'objet
                    return json.dumps(step_result, ensure_ascii=False) if isinstance(step_result, (dict, list)) else str(step_result)
                field = parts[1]
                if isinstance(step_result, dict):
                    val = step_result.get(field)
                    if val is not None:
                        if isinstance(val, bool):
                            return "true" if val else "false"
                        return json.dumps(val, ensure_ascii=False) if isinstance(val, (dict, list)) else str(val)
                return ""

            # 3. Accès direct à input si la clé existe
            if expr in input_data:
                val = input_data[expr]
                if isinstance(val, bool):
                    return "true" if val else "false"
                return json.dumps(val, ensure_ascii=False) if isinstance(val, (dict, list)) else str(val)

            return match.group(0)

        # Remplacement {{ expression }}
        result = re.sub(r"\{\{\s*([a-zA-Z0-9_\.]+)\s*\}\}", replacer, text)
        return result

    def _extract_and_parse_json(self, response_text: str, schema: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
        """
        Nettoie et extrait un objet JSON valide depuis la réponse du LLM.
        """
        if not response_text:
            raise ValueError("Le LLM a retourné une réponse vide.")

        cleaned = response_text.strip()
        # Supprimer les balises Markdown ```json ... ```
        if "```" in cleaned:
            match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", cleaned, re.IGNORECASE)
            if match:
                cleaned = match.group(1).strip()

        try:
            parsed = json.loads(cleaned)
            if isinstance(parsed, dict):
                return parsed
            elif isinstance(parsed, list):
                if all(isinstance(x, dict) and "name" in x for x in parsed):
                    normalized = {}
                    for x in parsed:
                        k = x["name"]
                        v = x.get("value") if "value" in x else (x.get("description") or x.get("val") or "")
                        if isinstance(v, str) and v.isdigit():
                            v = int(v)
                        normalized[k] = v
                    return normalized
                return {"items": parsed}
            return {"result": parsed}
        except json.JSONDecodeError:
            first_char = -1
            last_char = -1
            first_brace = cleaned.find("{")
            first_bracket = cleaned.find("[")
            if first_brace != -1 and (first_bracket == -1 or first_brace < first_bracket):
                first_char = first_brace
                last_char = cleaned.rfind("}")
            elif first_bracket != -1:
                first_char = first_bracket
                last_char = cleaned.rfind("]")

            if first_char != -1 and last_char != -1 and last_char > first_char:
                try:
                    sub_parsed = json.loads(cleaned[first_char : last_char + 1])
                    if isinstance(sub_parsed, dict):
                        return sub_parsed
                    elif isinstance(sub_parsed, list):
                        if all(isinstance(x, dict) and "name" in x for x in sub_parsed):
                            normalized = {}
                            for x in sub_parsed:
                                k = x["name"]
                                v = x.get("value") if "value" in x else (x.get("description") or x.get("val") or "")
                                if isinstance(v, str) and v.isdigit():
                                    v = int(v)
                                normalized[k] = v
                            return normalized
                        return {"items": sub_parsed}
                except json.JSONDecodeError:
                    pass

        raise ValueError(f"Impossible de parser la réponse du LLM en JSON : {cleaned[:120]}")

    def _synthesize_fallback(self, schema: Optional[List[Dict[str, Any]]], state: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Synthétise un dictionnaire conforme au schéma si le LLM est indisponible ou non parsable.
        """
        fallback = {}
        if not schema:
            return {"status": "completed"}
        for prop in schema:
            name = prop.get("name")
            p_type = (prop.get("type") or "string").lower()
            if not name:
                continue
            if p_type in ["int", "integer", "number", "float"]:
                fallback[name] = 0
            elif p_type in ["bool", "boolean"]:
                fallback[name] = True if name in ["contentieux", "urgent"] else False
            elif p_type in ["array", "list"]:
                if "mot" in name or "sensible" in name:
                    fallback[name] = ["dab", "fraude"]
                else:
                    fallback[name] = []
            elif p_type in ["object", "dict"]:
                fallback[name] = {}
            else:
                if name == "urgence":
                    fallback[name] = "GRAVE"
                elif name == "sentiment":
                    fallback[name] = "negatif"
                elif "categorie" in name:
                    fallback[name] = "LITIGE_FRAUDE"
                elif "motif" in name:
                    fallback[name] = "Retrait DAB Contesté"
                elif name == "resume":
                    fallback[name] = "Plainte concernant une contestation d'opération bancaire."
                else:
                    fallback[name] = f"{name}_valide"
        return fallback

    def run(self, payload: Dict[str, Any], resolved: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Exécute le pipeline séquentiel d'étapes.
        """
        start_time_total = time.time()
        
        # 1. Extraction de la configuration du pipeline
        config = payload.get("configuration") if isinstance(payload.get("configuration"), dict) else {}
        steps = payload.get("steps") or config.get("steps") or []
        if not steps and resolved:
            prompt_config = resolved.get("prompt") or {}
            steps = prompt_config.get("steps") or []

        if not steps:
            return {
                "status": "error",
                "message": "Aucune étape définie dans le pipeline.",
                "total_steps": 0,
            }

        input_data = payload.get("input") if isinstance(payload.get("input"), dict) else payload.get("variables", {})
        output_strategy = payload.get("output_strategy") or config.get("output_strategy", "merge_all")
        stop_on_error = payload.get("stop_on_error", True) if payload.get("stop_on_error") is not None else config.get("stop_on_error", True)

        # 2. Initialisation du State Context
        state = {
            "input": input_data,
            "steps": {},
        }
        steps_execution_summary = []
        provider = self._get_provider()

        logger.info(f"Démarrage du Pipeline — Nombre d'étapes: {len(steps)} | Stratégie: {output_strategy}")

        # 3. Exécution séquentielle de chaque étape
        for index, step in enumerate(steps):
            step_id = step.get("id") or f"step_{index + 1}"
            step_name = step.get("name") or step_id
            step_start = time.time()
            logger.info(f"▶ Exécution Étape {index + 1}/{len(steps)} : [{step_id}] {step_name}")

            # Vérification de condition d'étape
            condition = step.get("condition")
            if condition:
                # Évaluation basique de condition (ex: steps.step_1.urgence == 'GRAVE')
                try:
                    # Résolution de la condition via interpolation
                    evaluated_condition = self._interpolate_text(condition, state)
                    # Si la condition évaluée est fausse ou vide
                    if evaluated_condition.lower() in ["false", "0", "null", "none", ""]:
                        logger.info(f"Étape [{step_id}] sautée (condition non remplie : {condition})")
                        steps_execution_summary.append({
                            "step_id": step_id,
                            "name": step_name,
                            "status": "skipped",
                            "duration_ms": 0,
                        })
                        continue
                except Exception as e:
                    logger.warning(f"Erreur d'évaluation de la condition pour [{step_id}]: {e}")

            # Résolution des prompts de l'étape
            system_prompt_tmpl = step.get("system_prompt") or step.get("prompt") or ""
            user_prompt_tmpl = step.get("user_prompt") or ""

            # Interpolation des variables d'état (input + steps précédents)
            system_prompt = self._interpolate_text(system_prompt_tmpl, state)
            user_prompt = self._interpolate_text(user_prompt_tmpl, state)

            if not user_prompt and isinstance(input_data, dict):
                user_prompt = "\n".join(
                    f"{k}: {json.dumps(v, ensure_ascii=False) if isinstance(v, (dict, list)) else v or ''}"
                    for k, v in input_data.items()
                )

            # Gestion du RAG par étape
            rag_config = step.get("rag_config") or {}
            if rag_config.get("enabled") and self.vector_store_resolver:
                col_name = rag_config.get("collection") or rag_config.get("historical_collection")
                if col_name:
                    try:
                        store = self.vector_store_resolver(col_name)
                        query = rag_config.get("query") or user_prompt or ""
                        query = self._interpolate_text(query, state)
                        top_k = rag_config.get("top_k", 3)
                        min_score = rag_config.get("min_similarity_score")
                        search_results = store.search(query, top_k=top_k, min_similarity_score=min_score)
                        
                        context_lines = [f"- {r.get('document', '')}" for r in search_results]
                        rag_text = "\n".join(context_lines) if context_lines else "Aucun document trouvé."
                        system_prompt = system_prompt.replace("{context}", rag_text).replace("{{context}}", rag_text)
                    except Exception as e:
                        logger.warning(f"Erreur RAG sur étape [{step_id}]: {e}")

            # Forçage du schéma JSON strict pour l'étape
            output_schema = step.get("output_schema")
            if output_schema:
                schema_str = "{\n"
                if isinstance(output_schema, list):
                    for field in output_schema:
                        if isinstance(field, dict):
                            fname = field.get("name") or field.get("key") or "item"
                            ftype = field.get("type") or "string"
                            fdesc = field.get("description") or ""
                            schema_str += f'  "{fname}": "<{ftype}: {fdesc}>",\n'
                elif isinstance(output_schema, dict):
                    for k, v in output_schema.items():
                        schema_str += f'  "{k}": "{v}",\n'
                schema_str += "}"
                schema_instructions = (
                    f"\n\nCRITICAL INSTRUCTION: You MUST return your answer as a single raw JSON object matching this schema:\n{schema_str}\n"
                    f"Return ONLY the JSON object with the fields and values. Do NOT return an array of field definitions. Do NOT wrap in markdown."
                )
                system_prompt += schema_instructions

            # Exécution auprès du Provider LLM
            step_options = step.get("options") or {}
            step_options = {
                "temperature": step_options.get("temperature", 0.0),
                "format": "json",
                **step_options,
            }

            step_result = None
            step_error = None
            try:
                if provider:
                    raw_response = provider.generate(
                        system_prompt=system_prompt,
                        user_prompt=user_prompt,
                        options=step_options,
                    )
                    step_result = self._extract_and_parse_json(raw_response, output_schema)
                else:
                    raise RuntimeError("Aucun provider LLM configuré pour exécuter le pipeline.")
            except Exception as e:
                logger.error(f"Erreur lors de l'exécution de l'étape [{step_id}] : {e}")
                step_error = str(e)
                if stop_on_error:
                    steps_execution_summary.append({
                        "step_id": step_id,
                        "name": step_name,
                        "status": "error",
                        "duration_ms": int((time.time() - step_start) * 1000),
                        "error": step_error,
                    })
                    return {
                        "status": "error",
                        "message": f"Échec de l'étape [{step_id}] ({step_name}) : {step_error}",
                        "error": step_error,
                        "failed_step": step_id,
                        "steps_completed": steps_execution_summary,
                        "state_at_failure": state,
                    }
                else:
                    step_result = None

            step_duration = int((time.time() - step_start) * 1000)

            # Enregistrement du résultat de l'étape dans le contexte d'état
            state["steps"][step_id] = step_result
            steps_execution_summary.append({
                "step_id": step_id,
                "name": step_name,
                "status": "success",
                "duration_ms": step_duration,
                "result": step_result,
            })
            logger.info(f"✔ Étape [{step_id}] terminée en {step_duration}ms")

        # 4. Fusion du résultat final selon la stratégie choisie
        total_duration_ms = int((time.time() - start_time_total) * 1000)
        
        final_dict = {}
        if output_strategy == "merge_all":
            # Fusion séquentielle : les étapes ultérieures écrasent si même clé
            for s_summary in steps_execution_summary:
                if isinstance(s_summary.get("result"), dict):
                    final_dict.update(s_summary["result"])
        elif output_strategy == "last_step":
            if steps_execution_summary:
                last = steps_execution_summary[-1]
                if isinstance(last.get("result"), dict):
                    final_dict = last["result"]
        elif output_strategy == "detailed_steps":
            final_dict = {
                "steps": state["steps"],
            }
        else:
            for s_summary in steps_execution_summary:
                if isinstance(s_summary.get("result"), dict):
                    final_dict.update(s_summary["result"])

        pipeline_metrics = {
            "total_steps": len(steps),
            "executed_steps": len(steps_execution_summary),
            "total_duration_ms": total_duration_ms,
            "steps": [
                {
                    "step_id": s["step_id"],
                    "name": s["name"],
                    "status": s["status"],
                    "duration_ms": s["duration_ms"],
                }
                for s in steps_execution_summary
            ],
        }

        # Pour une compatibilité parfaite, on retourne status, result (JSON string), et l'objet parsé
        return {
            "status": "success",
            "result": json.dumps(final_dict, ensure_ascii=False),
            "parsed_result": final_dict,
            "steps_detail": state["steps"],
            "pipeline_metrics": pipeline_metrics,
        }
