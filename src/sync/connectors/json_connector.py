import json
import csv
import os
from typing import List, Dict, Any, Optional
from .base import BaseConnector


class JsonArrayConnector(BaseConnector):
    """Connecteur permettant d'extraire des enregistrements depuis une liste mémoire ou un fichier JSON/CSV."""

    def __init__(
        self,
        records: Optional[List[Dict[str, Any]]] = None,
        file_path: Optional[str] = None
    ):
        self.records = records
        self.file_path = file_path

    def fetch_records(self) -> List[Dict[str, Any]]:
        """Extrait les enregistrements soit depuis la liste passée, soit depuis le fichier."""
        if self.records is not None:
            return [r for r in self.records if isinstance(r, dict)]

        if self.file_path:
            if not os.path.exists(self.file_path):
                raise FileNotFoundError(f"Le fichier de données est introuvable : {self.file_path}")

            if self.file_path.endswith(".csv"):
                with open(self.file_path, mode="r", encoding="utf-8") as f:
                    reader = csv.DictReader(f)
                    return [dict(row) for row in reader]
            else:
                with open(self.file_path, mode="r", encoding="utf-8") as f:
                    content = json.load(f)
                    if isinstance(content, list):
                        return [r for r in content if isinstance(r, dict)]
                    elif isinstance(content, dict):
                        return [content]
                    return []

        return []
