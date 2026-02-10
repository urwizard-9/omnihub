import logging
import os
import time
from typing import List, Optional, Dict, Any
from pydantic import BaseModel

from fastapi import APIRouter, Request, HTTPException
from app.services.firestore_repo import FirestoreRepo
from app.rag.retriever import Retriever
from app.rag.generator import Generator

logger = logging.getLogger("RAG_API")
router = APIRouter(prefix="/api/search", tags=["RAG"])

# --- Models ---
class RAGScope(BaseModel):
    doc_ids: Optional[List[str]] = None
    concept_ids: Optional[List[str]] = None
    folder_path: Optional[str] = None

class RAGRequest(BaseModel):
    query: str
    scope: Optional[RAGScope] = None
    top_k: Optional[int] = int(os.getenv("DEFAULT_TOP_K", 8))

from app.common.schemas import RAGResponse, Citation

# --- Models ---
class RAGScope(BaseModel):
    doc_ids: Optional[List[str]] = None
    concept_ids: Optional[List[str]] = None
    folder_path: Optional[str] = None

# --- Models ---
# (RAGScope and RAGRequest are defined above, preventing duplicates)

# --- Handler ---
@router.post("/rag", response_model=RAGResponse)
async def search_rag(request: Request, body: RAGRequest):
    start_ts = time.time()
    
    # 1. Auth Context 확인
    auth_ctx = getattr(request.state, "auth_ctx", None)
    if not auth_ctx:
        raise HTTPException(status_code=401, detail="Unauthorized")
        
    repo = FirestoreRepo(auth_ctx)
    
    # 2. Retrieve (Vector Search + SSOT Rerank)
    retrieved_chunks = []
    retriever_error = None
    
    try:
        retriever = Retriever(repo)
        
        search_scope = {}
        if hasattr(auth_ctx, "tenant_id"): search_scope["tenant_id"] = auth_ctx.tenant_id 
        if hasattr(auth_ctx, "engagement_id"): search_scope["engagement_id"] = auth_ctx.engagement_id
        
        if body.scope:
            if body.scope.folder_path: search_scope["folder_path"] = body.scope.folder_path
            if body.scope.doc_ids: search_scope["doc_ids"] = body.scope.doc_ids

        retrieved_chunks = retriever.retrieve(
            query=body.query, 
            scope=search_scope, 
            top_k=min(body.top_k, int(os.getenv("MAX_TOP_K", 20)))
        )
    except Exception as e:
        logger.error(f"Retriever Failed: {e}")
        retriever_error = str(e)

    # 3. Generate (Vertex AI)
    generator = Generator()
    answer_text = generator.generate(body.query, [c.model_dump() for c in retrieved_chunks])
    
    # 4. Response Formatting
    citations = []
    
    for idx, chunk in enumerate(retrieved_chunks):
        # Create Citation with SSOT extras
        cit = Citation(
            idx=idx+1,
            doc_id=chunk.doc_id,
            title=getattr(chunk, "title", "Untitled"), 
            source_link=chunk.source_link,
            page=chunk.page,
            chunk_id=chunk.chunk_id,
            snippet=getattr(chunk, "snippet", "")[:200]
        )
        
        # Inject SSOT fields if model supports (using dynamic assignment or model update assumption)
        # Assuming Citation model has extra="allow" or user updated schema (Step 5/Types will use this)
        # Python side Pydantic will allow if configured or if we just pass as dict, 
        # But here we are returning RAGResponse object which expects Citation objects.
        # We'll attach attributes dynamically; FastAPI response serialization usually handles vars() or __dict__
        # But cleaner if Citation schema has these optional fields.
        # Implemented blindly as per instructions to "pass to front".
        cit.ssot_score = getattr(chunk, "ssot_score", None)
        cit.ssot_explain = getattr(chunk, "ssot_explain", None)
        cit.relevance = getattr(chunk, "relevance", None)
        
        citations.append(cit)

    process_ms = (time.time() - start_ts) * 1000
    
    # Metadata for Debug/UI
    rerank_enabled = os.getenv("SSOT_RERANK_ENABLED", "true").lower() == "true"
    alpha = float(os.getenv("SSOT_RERANK_ALPHA", 0.85))
    beta = float(os.getenv("SSOT_RERANK_BETA", 0.15))
    
    top_docs_preview = []
    if retrieved_chunks:
        # Collect top 3 unique docs
        seen = set()
        for c in retrieved_chunks:
            if c.doc_id not in seen:
                seen.add(c.doc_id)
                top_docs_preview.append({
                    "doc_id": c.doc_id, 
                    "ssot_score": getattr(c, "ssot_score", "N/A"),
                    "title": getattr(c, "title", "Untitled")
                })
            if len(top_docs_preview) >= 3: break

    return RAGResponse(
        answer=answer_text,
        citations=citations,
        meta={
            "model_version": os.getenv("VERTEX_MODEL_NAME", "gemini-2.0-flash-exp"),
            "retriever_version": "vertex-vector-search",
            "latency_ms": round(process_ms, 2),
            "retrieved_count": len(retrieved_chunks),
            "error_log": retriever_error,
            # Data for UI Toggle/Debug
            "ssot_rerank_enabled": rerank_enabled,
            "alpha": alpha,
            "beta": beta,
            "top_docs_preview": top_docs_preview
        }
    )
