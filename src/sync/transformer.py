import re
import hashlib
from typing import List, Dict, Any, Optional
from .schemas import DocumentTemplateConfig


class DocumentTransformer:
    """Moteur universel de transformation d'enregistrements bruts en documents textuels enrichis pour l'indexation RAG."""

    def __init__(self, config: DocumentTemplateConfig):
        self.config = config
        self.template = config.template
        self.id_field = config.id_field
        self.id_prefix = config.id_prefix or ""
        self.metadata_fields = config.metadata_fields or []
        self.source_name = config.source_name or "sync_engine"

    def _interpolate(self, record: Dict[str, Any]) -> str:
        """Remplace les variables {champ} par les valeurs correspondantes de manière résiliente."""
        result = self.template
        # Trouve tous les motifs {nom_de_cle}
        tokens = re.findall(r"\{([a-zA-Z0-9_\-\.]+)\}", self.template)
        for token in tokens:
            val = record.get(token)
            str_val = "" if val is None else str(val)
            result = result.replace(f"{{{token}}}", str_val)
        return result.strip()

    def _extract_id(self, record: Dict[str, Any], text: str) -> str:
        """Génère ou extrait un identifiant unique stable et idempotent."""
        if self.id_field and self.id_field in record and record[self.id_field] is not None:
            raw_id = str(record[self.id_field]).strip()
            return f"{self.id_prefix}{raw_id}"

        # Fallback : hachage déterministe SHA-256 du contenu textuel généré
        sha = hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]
        return f"{self.id_prefix}{sha}"

    def _extract_metadata(self, record: Dict[str, Any], doc_id: str) -> Dict[str, Any]:
        """Extrait et nettoie les métadonnées pour compatibilité ChromaDB."""
        meta: Dict[str, Any] = {
            "source": self.source_name,
            "doc_id": doc_id
        }

        for field in self.metadata_fields:
            if field in record:
                val = record[field]
                if isinstance(val, (str, int, float, bool)):
                    meta[field] = val
                elif val is None:
                    continue
                else:
                    meta[field] = str(val)

        return meta

    def transform_record(self, record: Dict[str, Any]) -> Dict[str, Any]:
        """Transforme un enregistrement unitaire en document indexable."""
        text = self._interpolate(record)
        doc_id = self._extract_id(record, text)
        metadata = self._extract_metadata(record, doc_id)

        return {
            "id": doc_id,
            "text": text,
            "metadata": metadata
        }

    def transform_all(self, records: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Transforme l'ensemble des enregistrements bruts."""
        documents = []
        for r in records:
            if not isinstance(r, dict):
                continue
            doc = self.transform_record(r)
            if doc["text"]:  # Ne conserve que les documents avec du contenu
                documents.append(doc)
        return documents
