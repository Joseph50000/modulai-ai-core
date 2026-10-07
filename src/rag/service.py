import time
import logging
from uuid import uuid4
from typing import Dict, Any, Optional, Generator, List

from src.rag.schemas import (
    RAGSearchRequest,
    RAGSearchResponse,
    RAGResolveRequest,
    RAGResolveResponse,
    SearchSourceItem,
)
from src.rag.vector_store import GenericVectorStore
from src.rag.context_aggregator import ContextAggregator
from src.rag.resolution_engine import ResolutionEngine

logger = logging.getLogger(__name__)

class RAGService:
    """
    Orchestrateur unifié pour la recherche sémantique multi-collections et la résolution assistée.
    """

    def __init__(self, llm_provider=None, vector_store_factory=None):
        if llm_provider is None:
            try:
                from src.providers.ollama_provider import OllamaProvider
                self.llm_provider = OllamaProvider()
            except Exception as e:
                logger.warning(f"Impossible d'initialiser OllamaProvider pour RAGService : {e}")
                self.llm_provider = None
        else:
            self.llm_provider = llm_provider

        self.vector_store_factory = vector_store_factory or (lambda col: GenericVectorStore(col))
        self.context_aggregator = ContextAggregator()
        self.resolution_engine = ResolutionEngine(llm_provider=self.llm_provider)

    def _get_store(self, collection_name: str) -> GenericVectorStore:
        return self.vector_store_factory(collection_name)

    def search(self, request: RAGSearchRequest) -> RAGSearchResponse:
        """Exécute une recherche sémantique avec filtres et score normalisé."""
        store = self._get_store(request.collection)
        raw_results = store.search(
            query=request.query,
            top_k=request.top_k,
            filter_metadata=request.filter_metadata,
            min_similarity_score=request.min_similarity_score
        )

        items = [
            SearchSourceItem(
                id=r["id"],
                document=r["document"],
                metadata=r.get("metadata", {}),
                distance=r.get("distance", 0.0),
                similarity_score=r.get("similarity_score", 0.0)
            )
            for r in raw_results
        ]

        return RAGSearchResponse(
            collection=request.collection,
            query=request.query,
            results=items,
            total_found=len(items)
        )

    def resolve(self, request: RAGResolveRequest) -> RAGResolveResponse:
        """Exécution synchrone de la résolution assistée."""
        start_time = time.time()
        correlation_id = request.correlation_id or str(uuid4())

        # 1. Recherche des cas historiques
        historical_matches = []
        if request.historical_collection and request.top_k_history > 0:
            hist_store = self._get_store(request.historical_collection)
            historical_matches = hist_store.search(
                query=request.query,
                top_k=request.top_k_history,
                filter_metadata=request.history_filter,
                min_similarity_score=request.min_similarity_score
            )

        # 2. Recherche des documents de référence
        documentary_matches = []
        if request.documentary_collection and request.top_k_docs > 0:
            doc_store = self._get_store(request.documentary_collection)
            documentary_matches = doc_store.search(
                query=request.query,
                top_k=request.top_k_docs,
                filter_metadata=request.documentary_filter,
                min_similarity_score=request.min_similarity_score
            )

        # 3. Formatage des contextes
        hist_context_text = self.context_aggregator.format_historical_context(
            historical_matches, request.target_solution_field
        )
        doc_context_text = self.context_aggregator.format_documentary_context(documentary_matches)
        comb_context_text = self.context_aggregator.format_combined_context(
            historical_matches, documentary_matches, request.target_solution_field
        )

        # 4. Résolution LLM
        reasoning, propositions, raw_message = self.resolution_engine.resolve(
            query=request.query,
            historical_context=hist_context_text,
            documentary_context=doc_context_text,
            combined_context=comb_context_text,
            num_propositions=request.num_propositions,
            system_role_instruction=request.system_role_instruction,
            custom_resolution_prompt=request.custom_resolution_prompt,
            model=request.model
        )

        execution_time_ms = int((time.time() - start_time) * 1000)

        hist_sources = [
            SearchSourceItem(
                id=h["id"],
                document=h["document"],
                metadata=h.get("metadata", {}),
                distance=h.get("distance", 0.0),
                similarity_score=h.get("similarity_score", 0.0)
            ) for h in historical_matches
        ]
        doc_sources = [
            SearchSourceItem(
                id=d["id"],
                document=d["document"],
                metadata=d.get("metadata", {}),
                distance=d.get("distance", 0.0),
                similarity_score=d.get("similarity_score", 0.0)
            ) for d in documentary_matches
        ]

        return RAGResolveResponse(
            status="success",
            reasoning=reasoning,
            propositions=propositions,
            raw_message=raw_message,
            historical_sources=hist_sources,
            documentary_sources=doc_sources,
            correlation_id=correlation_id,
            execution_time_ms=execution_time_ms
        )

    def resolve_stream(self, request: RAGResolveRequest) -> Generator[Dict[str, Any], None, None]:
        """Génération progressive Server-Sent Events (SSE)."""
        correlation_id = request.correlation_id or str(uuid4())

        yield {"type": "correlation", "correlation_id": correlation_id}

        # 1. Recherche des sources
        historical_matches = []
        if request.historical_collection and request.top_k_history > 0:
            hist_store = self._get_store(request.historical_collection)
            historical_matches = hist_store.search(
                query=request.query,
                top_k=request.top_k_history,
                filter_metadata=request.history_filter,
                min_similarity_score=request.min_similarity_score
            )

        documentary_matches = []
        if request.documentary_collection and request.top_k_docs > 0:
            doc_store = self._get_store(request.documentary_collection)
            documentary_matches = doc_store.search(
                query=request.query,
                top_k=request.top_k_docs,
                filter_metadata=request.documentary_filter,
                min_similarity_score=request.min_similarity_score
            )

        hist_sources = [
            SearchSourceItem(
                id=h["id"],
                document=h["document"],
                metadata=h.get("metadata", {}),
                distance=h.get("distance", 0.0),
                similarity_score=h.get("similarity_score", 0.0)
            ).model_dump() for h in historical_matches
        ]
        doc_sources = [
            SearchSourceItem(
                id=d["id"],
                document=d["document"],
                metadata=d.get("metadata", {}),
                distance=d.get("distance", 0.0),
                similarity_score=d.get("similarity_score", 0.0)
            ).model_dump() for d in documentary_matches
        ]

        # Émettre d'abord les sources identifiées
        yield {
            "type": "sources",
            "historical_sources": hist_sources,
            "documentary_sources": doc_sources,
            "correlation_id": correlation_id
        }

        # Si aucune source n'est disponible
        if not historical_matches and not documentary_matches:
            msg = "Aucune source historique ou documentaire trouvée pour cette situation."
            yield {"type": "chunk", "content": msg, "correlation_id": correlation_id}
            yield {"type": "final", "content": msg, "propositions": [], "reasoning": None, "correlation_id": correlation_id}
            return

        # 2. Formatage des contextes
        hist_context_text = self.context_aggregator.format_historical_context(
            historical_matches, request.target_solution_field
        )
        doc_context_text = self.context_aggregator.format_documentary_context(documentary_matches)
        comb_context_text = self.context_aggregator.format_combined_context(
            historical_matches, documentary_matches, request.target_solution_field
        )

        full_content = ""
        for chunk in self.resolution_engine.resolve_stream(
            query=request.query,
            historical_context=hist_context_text,
            documentary_context=doc_context_text,
            combined_context=comb_context_text,
            num_propositions=request.num_propositions,
            system_role_instruction=request.system_role_instruction,
            custom_resolution_prompt=request.custom_resolution_prompt,
            model=request.model
        ):
            full_content += chunk
            yield {"type": "chunk", "content": chunk, "correlation_id": correlation_id}

        reasoning, propositions = self.resolution_engine.parse_propositions(full_content)
        props_dump = [p.model_dump() for p in propositions]

        yield {
            "type": "final",
            "content": full_content,
            "reasoning": reasoning,
            "propositions": props_dump,
            "correlation_id": correlation_id
        }
