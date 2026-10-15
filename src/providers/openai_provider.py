import os
import json
import logging
import requests
from typing import Optional, Dict, Any, Generator

logger = logging.getLogger(__name__)

DEFAULT_CLOUD_MODEL = "qwen/qwen3.8-27b"
DEFAULT_CLOUD_URL = "https://api.groq.com/openai/v1"

class OpenAICompatibleProvider:
    """
    Provider LLM générique compatible avec l'API OpenAI Chat Completions (Groq, OpenAI, Mistral, vLLM, etc.).
    Permet d'exécuter des modèles Cloud sans dépendance externe lourde.
    """

    def __init__(
        self,
        base_url: Optional[str] = None,
        api_key: Optional[str] = None,
        default_model: Optional[str] = None,
        name: str = "Cloud LLM",
    ):
        self.name = name
        self.api_key = api_key or os.getenv("LLM_API_KEY") or os.getenv("GROQ_API_KEY") or ""
        raw_url = base_url or os.getenv("LLM_BASE_URL") or DEFAULT_CLOUD_URL
        self.base_url = raw_url.rstrip("/")
        self.default_model = default_model or os.getenv("LLM_MODEL_NAME") or DEFAULT_CLOUD_MODEL

    def _get_chat_url(self) -> str:
        if self.base_url.endswith("/chat/completions"):
            return self.base_url
        return f"{self.base_url}/chat/completions"

    def _get_headers(self) -> Dict[str, str]:
        headers = {
            "Content-Type": "application/json",
        }
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    def generate(
        self,
        system_prompt: str,
        user_prompt: str,
        model: Optional[str] = None,
        options: Optional[Dict[str, Any]] = None,
    ) -> str:
        """
        Exécute une génération via chat/completions de façon synchrone.
        """
        target_model = model or self.default_model or DEFAULT_CLOUD_MODEL
        opts = options or {}
        temperature = opts.get("temperature", 0.0)
        max_tokens = opts.get("max_tokens") or opts.get("num_predict")

        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": user_prompt or ""})

        payload = {
            "model": target_model,
            "messages": messages,
            "temperature": float(temperature) if temperature is not None else 0.0,
        }
        if max_tokens:
            payload["max_tokens"] = int(max_tokens)

        # Forçage du format JSON si demandé
        if opts.get("format") == "json":
            payload["response_format"] = {"type": "json_object"}

        url = self._get_chat_url()
        logger.info(f"Appel Cloud LLM [{self.name}] vers {url} (Modèle: {target_model})...")

        try:
            resp = requests.post(url, headers=self._get_headers(), json=payload, timeout=60)
            if not resp.ok:
                error_detail = resp.text
                try:
                    err_json = resp.json()
                    error_detail = err_json.get("error", {}).get("message") or resp.text
                except Exception:
                    pass
                raise RuntimeError(f"Erreur Provider Cloud ({resp.status_code}): {error_detail}")

            data = resp.json()
            choices = data.get("choices") or []
            if not choices:
                raise RuntimeError("Le provider Cloud n'a retourné aucun choix de réponse.")
            content = choices[0].get("message", {}).get("content", "")
            return content.strip()
        except requests.exceptions.RequestException as e:
            logger.error(f"Erreur de connexion Cloud LLM: {e}")
            raise RuntimeError(f"Échec de connexion au Provider Cloud LLM: {e}")

    def generate_stream(
        self,
        system_prompt: str,
        user_prompt: str,
        model: Optional[str] = None,
        options: Optional[Dict[str, Any]] = None,
    ) -> Generator[str, None, None]:
        """
        Exécute une génération streamée via chat/completions.
        """
        target_model = model or self.default_model or DEFAULT_CLOUD_MODEL
        opts = options or {}
        temperature = opts.get("temperature", 0.0)

        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": user_prompt or ""})

        payload = {
            "model": target_model,
            "messages": messages,
            "temperature": float(temperature) if temperature is not None else 0.0,
            "stream": True,
        }

        url = self._get_chat_url()
        try:
            resp = requests.post(url, headers=self._get_headers(), json=payload, stream=True, timeout=60)
            if not resp.ok:
                raise RuntimeError(f"Erreur Provider Cloud Stream ({resp.status_code}): {resp.text}")

            for line in resp.iter_lines():
                if not line:
                    continue
                decoded = line.decode("utf-8").strip()
                if decoded.startswith("data: "):
                    data_str = decoded[6:]
                    if data_str == "[DONE]":
                        break
                    try:
                        chunk = json.loads(data_str)
                        delta = chunk.get("choices", [{}])[0].get("delta", {}).get("content", "")
                        if delta:
                            yield delta
                    except Exception:
                        pass
        except Exception as e:
            logger.error(f"Erreur Cloud LLM Stream: {e}")
            raise e
