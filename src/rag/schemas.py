from typing import Optional, List, Dict, Any, Union
from pydantic import BaseModel, Field

class SearchSourceItem(BaseModel):
    id: str
    document: str
    metadata: Dict[str, Any] = Field(default_factory=dict)
    distance: float = 0.0
    similarity_score: float = Field(0.0, description="Score normalisé entre 0.0 et 1.0")

class RAGSearchRequest(BaseModel):
    collection: str = Field(..., description="Nom de la collection vectorielle cible")
    query: str = Field(..., description="Texte de la requête sémantique")
    top_k: int = Field(5, ge=1, le=50, description="Nombre maximal de résultats")
    min_similarity_score: Optional[float] = Field(None, ge=0.0, le=1.0, description="Seuil minimal de similarité (0.0 à 1.0)")
    filter_metadata: Optional[Dict[str, Any]] = Field(None, description="Filtres arbitraires sur métadonnées")

class RAGSearchResponse(BaseModel):
    collection: str
    query: str
    results: List[SearchSourceItem]
    total_found: int

class PropositionItem(BaseModel):
    index: int
    title: str = Field(..., description="Titre ou action recommandée")
    details: Optional[str] = Field(None, description="Justification ou commentaire explicatif")

class RAGResolveRequest(BaseModel):
    query: str = Field(..., description="Sujet ou texte du cas à résoudre")
    
    # Métadonnées ModulAI
    project_id: Optional[str] = None
    module_key: Optional[str] = None
    use_case_key: Optional[str] = None
    correlation_id: Optional[str] = None
    
    # Configuration des Collections (Agnostique, aucun nom en dur)
    historical_collection: Optional[str] = Field(None, description="Collection de cas passés / historiques")
    documentary_collection: Optional[str] = Field(None, description="Collection documentaire / institutionnelle")
    
    # Paramètres de Recherche & Filtrage
    top_k_history: int = Field(3, ge=0, le=20)
    top_k_docs: int = Field(3, ge=0, le=20)
    min_similarity_score: Optional[float] = Field(None, ge=0.0, le=1.0)
    history_filter: Optional[Dict[str, Any]] = None
    documentary_filter: Optional[Dict[str, Any]] = None
    
    # Paramétrage de la Résolution LLM
    num_propositions: int = Field(3, ge=1, le=10, description="Nombre de solutions souhaitées")
    system_role_instruction: Optional[str] = Field(None, description="Rôle injecté pour le modèle")
    custom_resolution_prompt: Optional[str] = Field(None, description="Gabarit surchargé du prompt de résolution")
    target_solution_field: Optional[str] = Field(None, description="Champ des métadonnées historiques contenant la solution passée")
    model: Optional[str] = None

class RAGResolveResponse(BaseModel):
    status: str = "success"
    reasoning: Optional[str] = Field(None, description="Analyse préalable de la situation")
    propositions: List[PropositionItem] = Field(default_factory=list, description="Liste des solutions structurées")
    raw_message: str = Field(..., description="Texte complet formaté")
    historical_sources: List[SearchSourceItem] = Field(default_factory=list)
    documentary_sources: List[SearchSourceItem] = Field(default_factory=list)
    correlation_id: str
    execution_time_ms: int
