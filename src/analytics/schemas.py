import uuid
from typing import List, Dict, Any, Optional, Union
from pydantic import BaseModel, Field

class FieldDefinition(BaseModel):
    name: str
    type: str = Field(default="string", description="Type: string, number, date, boolean")
    label: Optional[str] = None
    description: Optional[str] = None

class DatasetSchema(BaseModel):
    fields: List[FieldDefinition] = Field(default_factory=list)
    description: Optional[str] = None

class FilterClause(BaseModel):
    field: str
    operator: str = Field(default="eq", description="eq, neq, gt, gte, lt, lte, in, contains")
    value: Any

class MetricSpec(BaseModel):
    field: Optional[str] = None
    operation: str = Field(default="count", description="count, sum, avg, min, max")
    alias: str = "metric_val"
    label: Optional[str] = None

class AnalyticsIntent(BaseModel):
    chart_type: str = Field(default="bar", description="bar, line, pie, doughnut, area, stacked_bar, kpi")
    group_by: List[str] = Field(default_factory=list, description="Champs de dimension")
    metrics: List[MetricSpec] = Field(default_factory=list, description="Mesures calculées")
    filters: List[FilterClause] = Field(default_factory=list, description="Conditions de filtrage")
    sort_by: Optional[str] = None
    sort_order: str = Field(default="desc", description="asc ou desc")
    limit: Optional[int] = Field(default=10, description="Nombre max de lignes")
    title: str = "Analyse Statistique"
    subtitle: Optional[str] = None

class AnalyticsQueryRequest(BaseModel):
    query: str = Field(..., description="Question ou requête en langage naturel")
    dataset_schema: DatasetSchema = Field(default_factory=DatasetSchema)
    records: Optional[List[Dict[str, Any]]] = Field(default=None, description="Données tabulaires brutes à analyser")
    project_id: Optional[str] = None
    module_key: Optional[str] = None
    use_case_key: Optional[str] = None
    correlation_id: str = Field(default_factory=lambda: str(uuid.uuid4()))

class AnalyticsChartResponse(BaseModel):
    status: str = "success"
    intent: AnalyticsIntent
    echarts_option: Dict[str, Any]
    aggregated_data: List[Dict[str, Any]] = Field(default_factory=list)
    summary_insight: Optional[str] = None
    execution_time_ms: int = 0
    correlation_id: str
