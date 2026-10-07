from abc import ABC, abstractmethod
from typing import List, Dict, Any


class BaseConnector(ABC):
    """Interface abstraite universelle pour les connecteurs d'ingestion de données."""

    @abstractmethod
    def fetch_records(self) -> List[Dict[str, Any]]:
        """Extrait et renvoie une liste d'enregistrements bruts (dictionnaires)."""
        pass
