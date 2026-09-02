import os
import chromadb
from typing import List, Dict, Any, Optional
from sentence_transformers import SentenceTransformer
import logging

logger = logging.getLogger(__name__)

# Par défaut, stocker les données RAG dans un dossier data à la racine de fastapi
CHROMA_DB_PATH = os.getenv("CHROMA_DB_PATH", os.path.join(os.path.dirname(__file__), "..", "..", "data", "chroma_db"))

class GenericVectorStore:
    def __init__(self, collection_name: str, model_name: str = 'paraphrase-multilingual-MiniLM-L12-v2'):
        """
        Initialise un Vector Store générique.
        """
        logger.info(f"Initialisation du Vector Store pour la collection '{collection_name}' avec le modèle {model_name}")
        self.model = SentenceTransformer(model_name)
        
        os.makedirs(CHROMA_DB_PATH, exist_ok=True)
        
        self.chroma_client = chromadb.PersistentClient(path=CHROMA_DB_PATH)
        self.collection = self.chroma_client.get_or_create_collection(name=collection_name)

    def upsert_documents(self, documents: List[str], metadatas: List[Dict[str, Any]], ids: List[str]):
        """
        Insère ou met à jour des documents génériques de façon agnostique du métier.
        """
        if not documents:
            logger.warning("Aucun document à indexer.")
            return
            
        logger.info(f"Calcul des embeddings pour {len(documents)} documents...")
        embeds = self.model.encode(documents, convert_to_numpy=True).tolist()
        
        logger.info(f"Upsert dans la collection {self.collection.name}...")
        self.collection.upsert(
            ids=ids,
            embeddings=embeds,
            metadatas=metadatas,
            documents=documents
        )

    def search(self, query: str, top_k: int = 5, filter_metadata: Optional[Dict[str, Any]] = None):
        """
        Recherche sémantique générique.
        """
        logger.info(f"Recherche sémantique pour la requête: '{query}'")
        query_embedding = self.model.encode([query], convert_to_numpy=True).tolist()
        
        collection_count = self.collection.count()
        if collection_count == 0:
            return []
        results = self.collection.query(
            query_embeddings=query_embedding,
            n_results=min(max(1, top_k), collection_count),
            where=filter_metadata if filter_metadata else None
        )
        
        # Formatage générique des résultats
        formatted_results = []
        if results and results.get('documents') and len(results['documents'][0]) > 0:
            for idx in range(len(results['documents'][0])):
                formatted_results.append({
                    "id": results['ids'][0][idx],
                    "document": results['documents'][0][idx],
                    "metadata": results['metadatas'][0][idx] if results.get('metadatas') else {},
                    "distance": results['distances'][0][idx] if results.get('distances') else 0.0
                })
                
        return formatted_results

    def count(self) -> int:
        return self.collection.count()

    def inspect(self, limit: int = 100) -> Dict[str, Any]:
        """Retourne un aperçu borné de l’arborescence de la collection."""
        total = self.collection.count()
        if total == 0:
            return {"name": self.collection.name, "count": 0, "ids": [], "documents": [], "embeddings": [], "metadatas": []}
        result = self.collection.get(include=["documents", "embeddings", "metadatas"], limit=min(max(1, limit), 100))
        embeddings = result.get("embeddings") or []
        return {
            "name": self.collection.name,
            "count": total,
            "ids": result.get("ids") or [],
            "documents": result.get("documents") or [],
            "metadatas": result.get("metadatas") or [],
            "embeddings": embeddings,
            "embedding_dimensions": len(embeddings[0]) if embeddings else 0,
        }
