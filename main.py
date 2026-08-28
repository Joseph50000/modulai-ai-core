from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import Dict, Any, Optional
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
@app.get("/")
def read_root():
    return {"status": "online", "service": "ModulAI Core", "version": "1.0.0"}

@app.post("/api/execute")
def execute_use_case(payload: ExecutePayload):
    try:
        result = orchestrator.execute(payload.dict())
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8001, reload=True)
