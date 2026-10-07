import time
from typing import Dict, Any, List, Optional, Callable
from src.sync.schemas import SyncJobRequest, SyncJobResponse
from src.sync.connectors import get_connector
from src.sync.transformer import DocumentTransformer
from src.rag.vector_store import GenericVectorStore


class SyncService:
    """Orchestrateur universel d'ingestion et de synchronisation des données vers le VectorStore."""

    def __init__(self, vector_store_getter: Optional[Callable[[str], GenericVectorStore]] = None):
        self.vector_store_getter = vector_store_getter or (lambda col: GenericVectorStore(collection_name=col))

    def execute_job(self, request: SyncJobRequest) -> SyncJobResponse:
        start_time = time.time()
        errors: List[str] = []
        total_fetched = 0
        total_indexed = 0

        try:
            # 1. Extraction des données via le connecteur spécifié
            connector = get_connector(request.connector_type, request.connector_config)
            records = connector.fetch_records()
            total_fetched = len(records)

            if not records:
                execution_time = int((time.time() - start_time) * 1000)
                return SyncJobResponse(
                    status="success",
                    collection_name=request.collection_name,
                    total_fetched=0,
                    total_indexed=0,
                    errors=[],
                    execution_time_ms=execution_time
                )

            # 2. Transformation et interpolation des documents
            transformer = DocumentTransformer(request.template_config)
            transformed_docs = transformer.transform_all(records)

            if not transformed_docs:
                execution_time = int((time.time() - start_time) * 1000)
                return SyncJobResponse(
                    status="success",
                    collection_name=request.collection_name,
                    total_fetched=total_fetched,
                    total_indexed=0,
                    errors=["Aucun document textuel valide produit à partir des enregistrements."],
                    execution_time_ms=execution_time
                )

            # 3. Récupération et préparation du VectorStore
            store = self.vector_store_getter(request.collection_name)

            # Purge optionnelle des anciens enregistrements
            if request.clear_existing:
                if hasattr(store, "clear") and callable(store.clear):
                    store.clear()
                else:
                    try:
                        if hasattr(store, "chroma_client") and store.chroma_client:
                            store.chroma_client.delete_collection(request.collection_name)
                            store.collection = store.chroma_client.get_or_create_collection(name=request.collection_name)
                    except Exception as e:
                        errors.append(f"Avertissement lors de la purge de la collection: {e}")

            # 4. Upsert par lots (batching)
            batch_size = max(1, request.batch_size)
            for i in range(0, len(transformed_docs), batch_size):
                batch = transformed_docs[i:i + batch_size]
                doc_texts = [d["text"] for d in batch]
                metadatas = [d["metadata"] for d in batch]
                ids = [d["id"] for d in batch]

                try:
                    store.upsert_documents(documents=doc_texts, metadatas=metadatas, ids=ids)
                    total_indexed += len(batch)
                except Exception as b_err:
                    errors.append(f"Erreur d'indexation lot {i // batch_size + 1}: {b_err}")

            execution_time = int((time.time() - start_time) * 1000)
            status = "success" if not errors else ("partial" if total_indexed > 0 else "error")

            return SyncJobResponse(
                status=status,
                collection_name=request.collection_name,
                total_fetched=total_fetched,
                total_indexed=total_indexed,
                errors=errors,
                execution_time_ms=execution_time
            )

        except Exception as error:
            execution_time = int((time.time() - start_time) * 1000)
            return SyncJobResponse(
                status="error",
                collection_name=request.collection_name,
                total_fetched=total_fetched,
                total_indexed=total_indexed,
                errors=[str(error)],
                execution_time_ms=execution_time
            )
