import os
import base64
import csv
import io
import json
import requests
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import Dict, Any, Optional

load_dotenv()

from src.orchestrator import Orchestrator

app = FastAPI(
    title="ModulAI - AI Core FastAPI",
    description="Moteur générique d'exécution IA pour ModulAI.",
    version="1.0.0"
)

orchestrator = Orchestrator()

from src.audio import AudioTranscriptionService, TranscribeRequest, TranscribeResponse
audio_service = AudioTranscriptionService(llm_provider=orchestrator.provider)

from src.nlp import NLPService, NLPAnalyzeRequest, NLPAnalyzeResponse
nlp_service = NLPService(llm_provider=orchestrator.provider)

from src.rag import RAGService, RAGResolveRequest, RAGResolveResponse
rag_service = RAGService(llm_provider=orchestrator.provider, vector_store_factory=orchestrator.get_vector_store)

from src.analytics import AnalyticsService, AnalyticsQueryRequest, AnalyticsChartResponse, AnalyticsIntent
analytics_service = AnalyticsService(llm_provider=orchestrator.provider)

from src.sync import (
    SyncService,
    SyncScheduler,
    SyncJobRequest,
    SyncJobResponse,
    ScheduledJobSpec
)
sync_service = SyncService(vector_store_getter=orchestrator.get_vector_store)
sync_scheduler = SyncScheduler(sync_service=sync_service)

from typing import Dict, Any, Optional, List

class ExecutePayload(BaseModel):
    module: Optional[str] = None
    module_key: Optional[str] = None
    use_case: Optional[str] = None
    use_case_key: Optional[str] = None
    system_prompt_template: Optional[str] = None
    user_prompt: Optional[str] = None
    input: Optional[Dict[str, Any]] = None
    variables: Optional[Dict[str, Any]] = None
    output_schema: Optional[List[Dict[str, Any]]] = None
    rag_config: Optional[Dict[str, Any]] = None
    model_options: Optional[Dict[str, Any]] = None
    request_options: Optional[Dict[str, Any]] = None
    project_id: Optional[str] = None
    project_name: Optional[str] = None
    module_id: Optional[str] = None
    knowledge_base_id: Optional[str] = None
    knowledge_base_ids: Optional[List[str]] = None
    configuration: Optional[Dict[str, Any]] = None
    input_reference: Optional[Dict[str, Any]] = None
    context_reference: Optional[Dict[str, Any]] = None

class RagIndexPayload(BaseModel):
    collection: str
    documents: List[str]
    ids: List[str]
    metadatas: Optional[List[Dict[str, Any]]] = None

class RagSearchPayload(BaseModel):
    collection: str
    query: str
    top_k: int = 5
    filter_metadata: Optional[Dict[str, Any]] = None
    min_similarity_score: Optional[float] = None

class RagInspectPayload(BaseModel):
    collection: str
    limit: int = 100
    offset: int = 0

@app.get("/")
def read_root():
    return {"status": "online", "service": "ModulAI Core", "version": "1.0.0"}

@app.post("/api/rag/extract")
def extract_rag_file(payload: Dict[str, Any]):
    filename = str(payload.get("filename", ""))
    encoded = payload.get("content_base64")
    if not filename or not encoded:
        raise HTTPException(status_code=400, detail="filename and content_base64 are required")
    try:
        raw = base64.b64decode(encoded)
        extension = os.path.splitext(filename.lower())[1]
        if extension in {".txt", ".md", ".text", ".csv"}:
            text = raw.decode("utf-8-sig", errors="replace")
            if extension == ".csv":
                rows = list(csv.reader(io.StringIO(text)))
                text = "\n".join(" | ".join(row) for row in rows)
            extractor = "text-csv" if extension == ".csv" else "text"
        elif extension == ".pdf":
            from pypdf import PdfReader
            reader = PdfReader(io.BytesIO(raw))
            text = "\n\n".join((page.extract_text() or "") for page in reader.pages)
            extractor = "pypdf"
        elif extension == ".docx":
            from docx import Document
            document = Document(io.BytesIO(raw))
            paragraphs = [paragraph.text for paragraph in document.paragraphs if paragraph.text.strip()]
            tables = [" | ".join(cell.text.strip() for cell in row.cells) for table in document.tables for row in table.rows]
            text = "\n".join(paragraphs + tables)
            extractor = "python-docx"
        elif extension == ".xlsx":
            from openpyxl import load_workbook
            workbook = load_workbook(io.BytesIO(raw), read_only=True, data_only=True)
            sections = []
            for sheet in workbook.worksheets:
                sections.append(f"Feuille: {sheet.title}")
                for row in sheet.iter_rows(values_only=True):
                    values = [str(value) for value in row if value is not None]
                    if values:
                        sections.append(" | ".join(values))
            text = "\n".join(sections)
            extractor = "openpyxl"
        else:
            raise HTTPException(status_code=415, detail="Supported file types: PDF, DOCX, XLSX, CSV, TXT, MD")
        if not text.strip():
            raise HTTPException(status_code=422, detail="The extracted document is empty")
        return {"filename": filename, "type": extension.lstrip("."), "extractor": extractor, "text": text[:1000000]}
    except HTTPException:
        raise
    except ImportError as error:
        raise HTTPException(status_code=503, detail=f"Extractor dependency missing: {error.name}")
    except Exception as error:
        raise HTTPException(status_code=422, detail=f"File extraction failed: {error}")

@app.post("/api/rag/index")
def index_rag_documents(payload: RagIndexPayload):
    if not payload.documents:
        raise HTTPException(status_code=400, detail="documents must not be empty")
    if len(payload.documents) != len(payload.ids):
        raise HTTPException(status_code=400, detail="documents and ids must have the same length")
    metadatas = payload.metadatas or [{} for _ in payload.documents]
    if len(metadatas) != len(payload.documents):
        raise HTTPException(status_code=400, detail="metadatas and documents must have the same length")
    try:
        store = orchestrator.get_vector_store(payload.collection)
        store.upsert_documents(payload.documents, metadatas, payload.ids)
        return {"status": "indexed", "collection": payload.collection, "count": len(payload.documents), "total": store.count()}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"RAG indexing failed: {e}")

@app.post("/api/rag/search")
def search_rag_documents(payload: RagSearchPayload):
    try:
        store = orchestrator.get_vector_store(payload.collection)
        results = store.search(
            payload.query,
            top_k=max(1, min(payload.top_k, 50)),
            filter_metadata=payload.filter_metadata,
            min_similarity_score=payload.min_similarity_score
        )
        return {"collection": payload.collection, "query": payload.query, "results": results}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"RAG search failed: {e}")

@app.post("/api/rag/inspect")
def inspect_rag_collection(payload: RagInspectPayload):
    try:
        store = orchestrator.get_vector_store(payload.collection)
        return store.inspect(payload.limit, payload.offset)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"RAG inspection failed: {e}")

@app.post("/api/config/resolve")
def resolve_configuration(payload: ExecutePayload):
    """Prévisualise la configuration effective sans appeler de modèle ni modifier l’audit."""
    try:
        return orchestrator.config_resolver.resolve(payload.dict())["snapshot"]
    except Exception as error:
        raise HTTPException(status_code=500, detail=str(error))

@app.post("/api/execute")
def execute_use_case(payload: ExecutePayload):
    try:
        result = orchestrator.execute(payload.dict())
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/audio/transcribe", response_model=TranscribeResponse)
def transcribe_audio(payload: TranscribeRequest):
    if not payload.audio_base64:
        raise HTTPException(status_code=400, detail="audio_base64 est requis pour la transcription")
    try:
        audio_bytes = base64.b64decode(payload.audio_base64)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Échec de décodage base64: {e}")

    try:
        response = audio_service.process(audio_bytes=audio_bytes, request=payload)

        # Enregistrement d'audit vers le Backend Node.js
        try:
            audit_payload = {
                "project_id": payload.project_id,
                "module_name": payload.module_key,
                "use_case": payload.use_case_key or "audio-transcription",
                "prompt_name": payload.use_case_key or "audio-transcription",
                "provider": getattr(audio_service.transcription_provider, "provider", "whisper"),
                "model": getattr(audio_service.transcription_provider, "model", "whisper"),
                "status": "success",
                "execution_time": response.execution_time_ms,
                "user_name": "API User",
                "output": response.text,
                "resources_used": json.dumps({
                    "duration_seconds": response.duration_seconds,
                    "word_count": response.structure.word_count,
                    "correction_status": response.correction_status,
                }, ensure_ascii=False),
            }
            node_gateway_url = os.getenv("NODE_GATEWAY_URL", "http://localhost:3000/api")
            requests.post(f"{node_gateway_url}/aiexecution", json=audit_payload, timeout=(1, 2))
        except Exception:
            pass

        return response
    except ValueError as val_err:
        raise HTTPException(status_code=400, detail=str(val_err))
    except Exception as err:
        raise HTTPException(status_code=500, detail=str(err))

@app.post("/api/nlp/analyze", response_model=NLPAnalyzeResponse)
def analyze_nlp_text(payload: NLPAnalyzeRequest):
    if not payload.text or not payload.text.strip():
        raise HTTPException(status_code=400, detail="text est requis pour l'analyse NLP")

    try:
        response = nlp_service.process(payload)

        # Enregistrement d'audit vers le Backend Node.js
        try:
            audit_payload = {
                "project_id": payload.project_id,
                "module_name": payload.module_key,
                "use_case": payload.use_case_key or "nlp-analysis",
                "prompt_name": payload.use_case_key or "nlp-analysis",
                "provider": getattr(orchestrator.provider, "name", "ollama"),
                "model": getattr(orchestrator.provider, "default_model", "llama"),
                "status": "success",
                "execution_time": response.execution_time_ms,
                "user_name": "API User",
                "output": json.dumps({
                    "urgency": response.urgency,
                    "sentiment": response.sentiment,
                    "suggested_category": response.suggested_category,
                    "suggested_subcategory": response.suggested_subcategory,
                    "sensitive_keywords": response.sensitive_keywords_detected,
                }, ensure_ascii=False),
                "resources_used": json.dumps({
                    "words_count": len(payload.text.split()),
                    "sentiment_score": response.sentiment_score,
                }, ensure_ascii=False),
            }
            node_gateway_url = os.getenv("NODE_GATEWAY_URL", "http://localhost:3000/api")
            requests.post(f"{node_gateway_url}/aiexecution", json=audit_payload, timeout=(1, 2))
        except Exception:
            pass

        return response
    except ValueError as val_err:
        raise HTTPException(status_code=400, detail=str(val_err))
    except Exception as err:
        raise HTTPException(status_code=500, detail=str(err))

@app.post("/api/nlp/analyze/stream")
def analyze_nlp_text_stream(payload: NLPAnalyzeRequest):
    if not payload.text or not payload.text.strip():
        raise HTTPException(status_code=400, detail="text est requis pour l'analyse NLP")

    def event_generator():
        try:
            for event in nlp_service.process_stream(payload):
                yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'error': str(e)})}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")

@app.post("/api/rag/resolve", response_model=RAGResolveResponse)
def resolve_rag_case(payload: RAGResolveRequest):
    if not payload.query or not payload.query.strip():
        raise HTTPException(status_code=400, detail="query est requis pour la résolution RAG")

    try:
        response = rag_service.resolve(payload)

        # Enregistrement d'audit vers le Backend Node.js
        try:
            audit_payload = {
                "project_id": payload.project_id,
                "module_name": payload.module_key,
                "use_case": payload.use_case_key or "rag-resolution",
                "prompt_name": payload.use_case_key or "rag-resolution",
                "provider": getattr(orchestrator.provider, "name", "ollama"),
                "model": getattr(orchestrator.provider, "default_model", "llama"),
                "status": "success",
                "execution_time": response.execution_time_ms,
                "user_name": "API User",
                "output": json.dumps({
                    "reasoning": response.reasoning,
                    "propositions_count": len(response.propositions),
                    "historical_sources_count": len(response.historical_sources),
                    "documentary_sources_count": len(response.documentary_sources),
                }, ensure_ascii=False),
                "resources_used": json.dumps({
                    "query_length": len(payload.query),
                    "historical_collection": payload.historical_collection,
                    "documentary_collection": payload.documentary_collection,
                }, ensure_ascii=False),
            }
            node_gateway_url = os.getenv("NODE_GATEWAY_URL", "http://localhost:3000/api")
            requests.post(f"{node_gateway_url}/aiexecution", json=audit_payload, timeout=(1, 2))
        except Exception:
            pass

        return response
    except ValueError as val_err:
        raise HTTPException(status_code=400, detail=str(val_err))
    except Exception as err:
        raise HTTPException(status_code=500, detail=str(err))

@app.post("/api/rag/resolve/stream")
def resolve_rag_case_stream(payload: RAGResolveRequest):
    if not payload.query or not payload.query.strip():
        raise HTTPException(status_code=400, detail="query est requis pour la résolution RAG")

    def event_generator():
        try:
            for event in rag_service.resolve_stream(payload):
                yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'error': str(e)})}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")
 
@app.post("/api/analytics/query", response_model=AnalyticsIntent)
def extract_analytics_intent(payload: AnalyticsQueryRequest):
    if not payload.query or not payload.query.strip():
        raise HTTPException(status_code=400, detail="query est requis pour l'analyse analytique")
    try:
        intent = analytics_service.intent_engine.infer_intent(
            query=payload.query,
            schema=payload.dataset_schema
        )
        return intent
    except Exception as err:
        raise HTTPException(status_code=500, detail=str(err))

@app.post("/api/analytics/chart", response_model=AnalyticsChartResponse)
def generate_analytics_chart(payload: AnalyticsQueryRequest):
    if not payload.query or not payload.query.strip():
        raise HTTPException(status_code=400, detail="query est requis pour la génération de graphique")

    try:
        response = analytics_service.process_query(payload)

        # Enregistrement d'audit vers le Backend Node.js
        try:
            audit_payload = {
                "project_id": payload.project_id,
                "module_name": payload.module_key,
                "use_case": payload.use_case_key or "analytics-chart",
                "prompt_name": payload.use_case_key or "analytics-chart",
                "provider": getattr(orchestrator.provider, "name", "ollama"),
                "model": getattr(orchestrator.provider, "default_model", "llama"),
                "status": "success",
                "execution_time": response.execution_time_ms,
                "user_name": "API User",
                "output": json.dumps({
                    "chart_type": response.intent.chart_type,
                    "title": response.intent.title,
                    "aggregated_rows": len(response.aggregated_data),
                    "insight": response.summary_insight
                }, ensure_ascii=False),
                "resources_used": json.dumps({
                    "query_length": len(payload.query),
                    "records_count": len(payload.records) if payload.records else 0,
                    "fields_count": len(payload.dataset_schema.fields) if payload.dataset_schema else 0,
                }, ensure_ascii=False),
            }
            node_gateway_url = os.getenv("NODE_GATEWAY_URL", "http://localhost:3000/api")
            requests.post(f"{node_gateway_url}/aiexecution", json=audit_payload, timeout=(1, 2))
        except Exception:
            pass

        return response
    except ValueError as val_err:
        raise HTTPException(status_code=400, detail=str(val_err))
    except Exception as err:
        raise HTTPException(status_code=500, detail=str(err))

# ============================================================================
# Core Ingestion & Sync Framework Endpoints
# ============================================================================

@app.post("/api/sync/execute", response_model=SyncJobResponse)
def execute_sync_job(payload: SyncJobRequest):
    """Exécute un job d'ingestion et de synchronisation vers le VectorStore à la demande."""
    try:
        response = sync_service.execute_job(payload)
        return response
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur d'exécution de la synchronisation: {e}")

@app.post("/api/sync/schedule")
def schedule_sync_job(payload: ScheduledJobSpec):
    """Enregistre ou met à jour une tâche de synchronisation récurrente."""
    try:
        result = sync_scheduler.add_sync_job(payload)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur de planification du job: {e}")

@app.get("/api/sync/jobs")
def list_sync_jobs():
    """Liste tous les jobs de synchronisation planifiés actifs."""
    try:
        return {"jobs": sync_scheduler.list_jobs()}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur de récupération des jobs: {e}")

@app.delete("/api/sync/jobs/{job_id}")
def delete_sync_job(job_id: str):
    """Supprime un job planifié existant."""
    removed = sync_scheduler.remove_sync_job(job_id)
    if not removed:
        raise HTTPException(status_code=404, detail=f"Job '{job_id}' introuvable")
    return {"status": "deleted", "job_id": job_id}

@app.post("/api/sync/jobs/{job_id}/trigger", response_model=SyncJobResponse)
def trigger_scheduled_job(job_id: str):
    """Déclenche manuellement un job planifié enregistré."""
    try:
        return sync_scheduler.trigger_job(job_id)
    except ValueError as ve:
        raise HTTPException(status_code=404, detail=str(ve))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host=os.getenv("AI_CORE_HOST", "0.0.0.0"),
        port=int(os.getenv("AI_CORE_PORT", "8001")),
        reload=os.getenv("AI_CORE_RELOAD", "true").lower() == "true",
    )
