from typing import Optional
from pydantic_settings import BaseSettings, SettingsConfigDict
import os
from pathlib import Path

# Calculate .env path relative to this config.py file
# config.py is in backend/app/core/, so we go up 2 levels to backend/
_config_dir = Path(__file__).parent  # backend/app/core/
_backend_dir = _config_dir.parent.parent  # backend/
_env_file_path = _backend_dir / ".env"

class Settings(BaseSettings):
    PROJECT_NAME: str = "OmniHub"
    PROJECT_ID: str  =""  #외부에서 설정(cloud run)
    SUPER_ADMIN_EMAIL: str = "" # Super Admin Email for initial setup
    
    # Default to service_account.json in the backend root if not set in env
    # GOOGLE_APPLICATION_CREDENTIALS: Optional for Cloud Run (ADC), Required for Local if no gcloud auth
    GOOGLE_APPLICATION_CREDENTIALS: Optional[str] = None
    
    # OAuth 2.0 (From Google Cloud Console)
    GOOGLE_CLIENT_ID: str = "" 
    GOOGLE_CLIENT_SECRET: str = ""
    SECRET_KEY: str = "" # For signing internal JWT
    ALGORITHM: str = "HS256"

    SECTION_DOCAI: str = "Document AI Settings"
    DOCAI_LOCATION: str = "" # Default location
    DOCAI_PROCESSOR_ID: str = "" # Set via env or .env file

    # RAG - Storage & DB
    FIRESTORE_DATABASE: str = "(default)"
    GCS_BUCKET: str = ""
    GCS_PREFIX: str = "omnihub-data"

    # RAG - Tenant & Scope
    TENANT_ID: str = "default"
    ENGAGEMENT_ID: str = "default"
    
    # RAG - DocAI
    DOC_AI_LOCATION: str = "us"
    DOC_AI_PROCESSOR_ID_PDF: Optional[str] = None
    DOC_AI_PROCESSOR_ID_IMAGE: Optional[str] = None
    CHUNK_SIZE_HINT: int = 1000
    CHUNK_OVERLAP_HINT: int = 200

    # RAG - AI & Embedding
    VERTEX_LOCATION: str = "us-central1"
    VERTEX_MODEL_NAME: str = "gemini-1.5-flash-001"
    VERTEX_EMBED_MODEL: str = "text-embedding-004"
    EMBEDDING_PROVIDER: str = "vertex" # vertex or openai

    # RAG - Vector Search
    VECTOR_INDEX_NAME: Optional[str] = None
    VECTOR_INDEX_ENDPOINT: Optional[str] = None
    VECTOR_DEPLOYED_INDEX_ID: Optional[str] = None
    VECTOR_DIM: int = 768
    VECTOR_UPSERT_BATCH_SIZE: int = 50

    # RAG - Logic Versions & Caps
    PIPELINE_VERSION: str = "v1"
    POLICY_RULE_VERSION: str = "v1"
    CONCEPT_RULES_VERSION: str = "v1"
    EDGE_RANKER_VERSION: str = "v1"
    DOC_INDEX_VERSION: str = "v1"
    
    TOP_CONCEPTS_CAP: int = 50
    PER_DOC_CAP: int = 50
    
    # Graph Serving & Optimization
    PER_DOC_TOP_CONCEPTS: int = 15 # Ranker Output Cap
    GRAPH_SERVING_CAP: int = 20    # Serving API Cap
    GRAPH_SERVING_ALLOWED_STATUSES: str = "APPROVED" # Comma sep string
    MAX_PER_CONCEPT_TYPE: int = 5
    
    # Concept Co-occurrence
    COOC_DOC_TOPK: int = 10
    COOC_MIN_SHARED_DOCS: int = 2
    COOC_MIN_WEIGHT: float = 1.0
    COOC_NEIGHBOR_CAP: int = 20
    
    model_config = SettingsConfigDict(
        env_file=str(_env_file_path),
        env_file_encoding='utf-8',
        extra="ignore"
    )

settings = Settings()
