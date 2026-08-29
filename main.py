import os
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
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

from typing import Dict, Any, Optional, List

class ExecutePayload(BaseModel):
    module: str
    use_case: str
    system_prompt_template: Optional[str] = None
    user_prompt: Optional[str] = None
    variables: Optional[Dict[str, Any]] = None
    output_schema: Optional[List[Dict[str, Any]]] = None
    rag_config: Optional[Dict[str, Any]] = None
    model_options: Optional[Dict[str, Any]] = None
    project_id: Optional[str] = None
    project_name: Optional[str] = None
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

@app.get("/")
def read_root():
    return {"status": "online", "service": "ModulAI Core", "version": "1.0.0"}

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
        results = store.search(payload.query, top_k=max(1, min(payload.top_k, 20)), filter_metadata=payload.filter_metadata)
        return {"collection": payload.collection, "query": payload.query, "results": results}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"RAG search failed: {e}")

@app.post("/api/execute")
def execute_use_case(payload: ExecutePayload):
    try:
        result = orchestrator.execute(payload.dict())
        return result
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
