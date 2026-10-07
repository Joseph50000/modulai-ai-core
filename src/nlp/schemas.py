from typing import Optional, List, Dict, Any, Union
from pydantic import BaseModel, Field

class TaxonomySubcategory(BaseModel):
    id: Optional[str] = None
    label: str
    description: Optional[str] = None
    severity: Optional[str] = None

class TaxonomyCategory(BaseModel):
    id: Optional[str] = None
    label: str
    description: Optional[str] = None
    subcategories: List[TaxonomySubcategory] = Field(default_factory=list)

class NLPAnalyzeRequest(BaseModel):
    text: str = Field(..., description="Texte à analyser")
    
    # Métadonnées & Contexte ModulAI
    project_id: Optional[str] = None
    module_key: Optional[str] = None
    use_case_key: Optional[str] = None
    correlation_id: Optional[str] = None
    
    # Paramètres de Domaine Dynamiques (Zéro codé en dur dans le Core)
    taxonomy: Optional[Dict[str, Any]] = Field(
        None, 
        description="Arborescence des catégories et sous-catégories/motifs"
    )
    sensitive_keywords: Optional[List[str]] = Field(
        default_factory=list, 
        description="Liste dynamique des mots critiques / sensibles"
    )
    urgency_levels: Optional[List[str]] = Field(
        default=["MINEUR", "MOYEN", "GRAVE"],
        description="Échelle de gravité autorisée (ex: MINEUR, MOYEN, GRAVE ou LOW, MEDIUM, HIGH, CRITICAL)"
    )
    context_nature: Optional[str] = Field("DOSSIER", description="Nature du dossier (ex: INCIDENT, TICKET, FEEDBACK)")
    context_definition: Optional[str] = Field("", description="Définition du contexte pour guider le LLM")
    
    # Options d'analyse
    enable_llm_reasoning: bool = Field(True, description="Active le raisonnement LLM pour l'urgence et la classification")
    generate_summary: bool = Field(True, description="Active la génération de résumé")
    summary_type: str = Field("extractive", description="extractive ou abstractive")
    max_summary_words: int = Field(50, description="Nombre maximal de mots pour le résumé")
    language: str = Field("fr", description="Langue principale du texte")

class NLPAnalyzeResponse(BaseModel):
    status: str = "success"
    urgency: str = Field(..., description="Niveau d'urgence/gravité calculé")
    sentiment: str = Field(..., description="Tonalité globale (ex: tres_negatif, negatif, neutre, positif)")
    sentiment_score: float = Field(0.0, description="Score numérique de polarité (-1.0 à 1.0)")
    sensitive_keywords_detected: List[str] = Field(default_factory=list, description="Mots sensibles détectés")
    summary: Optional[str] = Field(None, description="Résumé du texte")
    suggested_category: str = Field("AUTRE", description="Catégorie identifiée")
    suggested_subcategory: str = Field("AUTRE", description="Sous-catégorie ou motif identifié")
    classification_reasoning: Optional[str] = Field("Aucune explication", description="Justification du choix de classification")
    urgency_reasoning: Optional[str] = Field("Aucune explication", description="Justification du niveau d'urgence")
    correlation_id: str = Field(..., description="Identifiant unique de corrélation")
    execution_time_ms: int = Field(0, description="Durée totale d'exécution en millisecondes")
