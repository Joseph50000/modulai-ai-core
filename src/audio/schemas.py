from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field


class AudioSegment(BaseModel):
    id: Optional[int] = None
    start: Optional[float] = None
    end: Optional[float] = None
    speaker: Optional[str] = None
    text: str


class TextStructure(BaseModel):
    paragraphs: List[Dict[str, Any]] = Field(default_factory=list)
    paragraph_count: int = 0
    sentence_count: int = 0
    word_count: int = 0
    character_count: int = 0


class TranscribeRequest(BaseModel):
    # Fichier audio en Base64 si appel JSON
    audio_base64: Optional[str] = Field(None, description="Données audio encodées en base64")
    filename: Optional[str] = Field("audio.mp3", description="Nom du fichier avec extension")

    # Identifiants ModulAI
    project_id: Optional[str] = None
    module_key: Optional[str] = None
    use_case_key: Optional[str] = None

    # Paramètres de transcription
    language: Optional[str] = Field("fr", description="Code langue ISO (ex: fr, en)")
    vocabulary_terms: Optional[List[str]] = Field(default_factory=list, description="Liste dynamique de termes métier autorisés")
    enable_correction: bool = Field(True, description="Active la correction phonétique/orthographique par LLM")
    diarization: bool = Field(False, description="Active la labellisation des locuteurs")
    speaker_roles: Optional[List[str]] = Field(None, description="Rôles personnalisés à attribuer aux locuteurs")
    custom_correction_prompt: Optional[str] = Field(None, description="Prompt de correction personnalisé pour ce cas d'usage")


class TranscribeResponse(BaseModel):
    status: str = "success"
    text: str = Field(..., description="Texte final transcrit et corrigé")
    raw_text: str = Field(..., description="Texte brut sorti de Whisper")
    correction_status: str = Field(..., description="APPLIED, REVIEW_REQUIRED, ou DISABLED")
    review_reason: Optional[str] = None
    duration_seconds: Optional[float] = None
    segments: List[AudioSegment] = Field(default_factory=list)
    speakers: List[str] = Field(default_factory=list)
    structure: TextStructure
    execution_time_ms: int = 0
