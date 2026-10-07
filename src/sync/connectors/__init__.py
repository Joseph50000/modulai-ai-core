from typing import Dict, Any
from .base import BaseConnector
from .rest_connector import RestConnector
from .json_connector import JsonArrayConnector


def get_connector(connector_type: str, config: Dict[str, Any]) -> BaseConnector:
    """Factory instanciant le connecteur de données approprié."""
    c_type = (connector_type or "json").lower()

    if c_type in ("json", "json_array", "memory"):
        return JsonArrayConnector(
            records=config.get("records"),
            file_path=config.get("file_path")
        )
    elif c_type == "rest":
        return RestConnector(
            url=config.get("url", ""),
            method=config.get("method", "GET"),
            headers=config.get("headers"),
            params=config.get("params"),
            body=config.get("body"),
            items_path=config.get("items_path"),
            timeout=config.get("timeout", 30)
        )
    else:
        raise ValueError(f"Type de connecteur non pris en charge : '{connector_type}'")


__all__ = ["BaseConnector", "RestConnector", "JsonArrayConnector", "get_connector"]
