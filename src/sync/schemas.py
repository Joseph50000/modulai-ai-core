import datetime
from enum import Enum
from typing import Dict, Any, List, Optional
from pydantic import BaseModel, Field


class ConnectorType(str, Enum):
    JSON = "json"
    REST = "rest"
    SQL = "sql"


class RestConnectorConfig(BaseModel):
    url: str
    method: str = "GET"
    headers: Optional[Dict[str, str]] = None
    params: Optional[Dict[str, Any]] = None
    body: Optional[Dict[str, Any]] = None
    items_path: Optional[str] = None


class JsonConnectorConfig(BaseModel):
    records: Optional[List[Dict[str, Any]]] = None
    file_path: Optional[str] = None


class SqlConnectorConfig(BaseModel):
    query: Optional[str] = None
    connection_string: Optional[str] = None
    preset: Optional[str] = None


class DocumentTemplateConfig(BaseModel):
    template: str
    id_field: Optional[str] = None
    id_prefix: Optional[str] = ""
    metadata_fields: List[str] = Field(default_factory=list)
    source_name: Optional[str] = None


class SyncJobRequest(BaseModel):
    collection_name: str
    connector_type: str = "json"
    connector_config: Dict[str, Any] = Field(default_factory=dict)
    template_config: DocumentTemplateConfig
    batch_size: int = 100
    clear_existing: bool = False
    project_id: Optional[str] = None
    module_key: Optional[str] = None


class SyncJobResponse(BaseModel):
    status: str
    collection_name: str
    total_fetched: int
    total_indexed: int
    errors: List[str] = Field(default_factory=list)
    execution_time_ms: int = 0
    timestamp: str = Field(default_factory=lambda: datetime.datetime.now(datetime.timezone.utc).isoformat())


class ScheduledJobSpec(BaseModel):
    job_id: str
    cron_expression: Optional[str] = None
    interval_seconds: Optional[int] = None
    sync_request: SyncJobRequest
