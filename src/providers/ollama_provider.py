import os
import logging
from ollama import Client

logger = logging.getLogger(__name__)

class OllamaProvider:
    def __init__(self, base_url: str = None, api_key: str = None, default_model: str = None):
        self.base_url = base_url or os.getenv("LLM_BASE_URL", "http://127.0.0.1:11434")
        api_key = api_key or os.getenv("LLM_API_KEY", "")
        self.default_model = default_model or os.getenv("LLM_MODEL_NAME", "llama3.2:1b")
        
        headers = {}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
            
        self.client = Client(host=self.base_url, headers=headers)

    def generate(self, system_prompt: str, user_prompt: str, model: str = None, options: dict = None) -> str:
        """
        Exécute un prompt via le provider Ollama de façon agnostique du métier.
        """
        target_model = model or self.default_model
        opts = options or {'temperature': 0}
        
        try:
            logger.info(f"Appel générique à Ollama (Modèle: {target_model})...")
            response = self.client.chat(model=target_model, messages=[
                {'role': 'system', 'content': system_prompt},
                {'role': 'user', 'content': user_prompt}
            ], options=opts)
            
            return response['message']['content'].strip()
        except Exception as e:
            logger.error(f"Erreur lors de l'appel au Provider Ollama : {e}")
            raise e

    def generate_stream(self, system_prompt: str, user_prompt: str, model: str = None, options: dict = None):
        """
        Exécute un prompt via le provider Ollama et retourne le résultat en stream.
        """
        target_model = model or self.default_model
        opts = options or {'temperature': 0}
        
        try:
            response = self.client.chat(model=target_model, messages=[
                {'role': 'system', 'content': system_prompt},
                {'role': 'user', 'content': user_prompt}
            ], options=opts, stream=True)
            
            for chunk in response:
                yield chunk['message']['content']
        except Exception as e:
            logger.error(f"Erreur lors de l'appel au Provider Ollama (Stream) : {e}")
            raise e
