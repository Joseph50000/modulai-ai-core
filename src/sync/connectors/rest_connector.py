from typing import List, Dict, Any, Optional
import requests
from .base import BaseConnector


class RestConnector(BaseConnector):
    """Connecteur REST universel permettant d'extraire des enregistrements via API HTTP."""

    def __init__(
        self,
        url: str,
        method: str = "GET",
        headers: Optional[Dict[str, str]] = None,
        params: Optional[Dict[str, Any]] = None,
        body: Optional[Dict[str, Any]] = None,
        items_path: Optional[str] = None,
        timeout: int = 30
    ):
        self.url = url
        self.method = method.upper()
        self.headers = headers or {}
        self.params = params or {}
        self.body = body
        self.items_path = items_path
        self.timeout = timeout

    def _extract_items(self, data: Any) -> List[Dict[str, Any]]:
        """Extrait la liste d'éléments depuis une structure JSON selon items_path."""
        if not self.items_path:
            if isinstance(data, list):
                return [item for item in data if isinstance(item, dict)]
            if isinstance(data, dict):
                # Cherche une clé de liste évidente s'il y en a une seule
                for val in data.values():
                    if isinstance(val, list):
                        return [item for item in val if isinstance(item, dict)]
                return [data]
            return []

        current = data
        for part in self.items_path.split("."):
            part = part.strip()
            if not part:
                continue
            if isinstance(current, dict) and part in current:
                current = current[part]
            else:
                return []

        if isinstance(current, list):
            return [item for item in current if isinstance(item, dict)]
        elif isinstance(current, dict):
            return [current]
        return []

    def fetch_records(self) -> List[Dict[str, Any]]:
        """Exécute la requête HTTP et renvoie les enregistrements extraits."""
        try:
            if self.method == "POST":
                resp = requests.post(
                    self.url,
                    json=self.body,
                    params=self.params,
                    headers=self.headers,
                    timeout=self.timeout
                )
            else:
                resp = requests.get(
                    self.url,
                    params=self.params,
                    headers=self.headers,
                    timeout=self.timeout
                )

            resp.raise_for_status()
            data = resp.json()
            return self._extract_items(data)
        except Exception as error:
            raise RuntimeError(f"Erreur d'extraction REST depuis {self.url}: {error}") from error
