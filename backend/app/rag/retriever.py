import os
import logging
from typing import List, Any, Dict, Optional
from pydantic import BaseModel
from google.cloud import aiplatform
from vertexai.language_models import TextEmbeddingModel  # Or use your preferred client
from app.services.firestore_repo import FirestoreRepo
from app.common.schemas import Evidence

# (실제 구현 시 RAGScope 모델은 rag_api.py와 공유 필요. 여기선 Dict로 처리)

logger = logging.getLogger("Retriever")

# --- Env Config ---
PROJECT_ID = os.getenv("GCP_PROJECT_ID")
LOCATION = os.getenv("VERTEX_LOCATION", "us-central1")
INDEX_ENDPOINT_NAME = os.getenv("VECTOR_INDEX_ENDPOINT") # projects/.../indexEndpoints/...
DEPLOYED_INDEX_ID = os.getenv("VECTOR_DEPLOYED_INDEX_ID")
EMBED_MODEL_NAME = os.getenv("VERTEX_EMBED_MODEL", "text-embedding-004")

# Tuning Params
TOPK_MULT = int(os.getenv("RETRIEVER_TOPK_MULT", 3))
PER_DOC_CAP = int(os.getenv("PER_DOC_CHUNK_CAP", 2))

class RetrievedChunk(BaseModel):
    doc_id: str
    chunk_id: str
    score: float
    text: str # snippet
    page: Optional[int] = 1
    doc_title: Optional[str] = None
    source_link: Optional[str] = None
    security_level: Optional[str] = None
    
class Retriever:
    def __init__(self, repo: FirestoreRepo):
        self.repo = repo
        
        # Initialize Vertex AI
        # Force credentials if available in settings
        from google.oauth2 import service_account
        from app.core.config import settings
        
        creds = None
        if settings.GOOGLE_APPLICATION_CREDENTIALS:
             creds = service_account.Credentials.from_service_account_file(settings.GOOGLE_APPLICATION_CREDENTIALS)

        aiplatform.init(project=PROJECT_ID, location=LOCATION, credentials=creds)
        self.idx_client = aiplatform.MatchingEngineIndexEndpoint(index_endpoint_name=INDEX_ENDPOINT_NAME)
        self.embed_model = TextEmbeddingModel.from_pretrained(EMBED_MODEL_NAME)

    def _embed_query(self, query: str) -> List[float]:
        try:
            embeddings = self.embed_model.get_embeddings([query])
            return embeddings[0].values
        except Exception as e:
            logger.error(f"Embedding Generation Failed: {e}")
            raise

    def retrieve(self, query: str, scope: Any = None, top_k: int = 5) -> List[Evidence]:
        """
        Main Retrieval Pipeline with SSOT Reranking
        1. Embed Query
        2. Vector Search (fetch more candidates)
        3. Rerank (Vector Score + SSOT Score)
        4. Post-Processing (Dedup, Diversity, Meta Injection)
        """
        # Config (Rerank)
        RERANK_ENABLED = os.getenv("SSOT_RERANK_ENABLED", "true").lower() == "true"
        ALPHA = float(os.getenv("SSOT_RERANK_ALPHA", 0.85))
        BETA = float(os.getenv("SSOT_RERANK_BETA", 0.15))

        # 1. Embed
        query_vec = self._embed_query(query)
        
        # 2. Build Filter (Strict Filters: Tenant/Engagement)
        restricts = []
        # (Namespace logic omitted for brevity, same as before)
        # Note: If you have existing namespace logic, keep it here.
        # Assuming minimal implementation for now or use user's context if provided.
        # Ideally, `scope` should be parsed to restricts.
        
        # 3. Search (Fetch detailed candidates for reranking)
        search_k = top_k * TOPK_MULT
        
        try:
            # Note: actual call might differ based on SDK version
            neighbors = self.idx_client.find_neighbors(
                deployed_index_id=DEPLOYED_INDEX_ID,
                queries=[query_vec],
                num_neighbors=search_k,
                filter=restricts if restricts else None 
            )
        except Exception as e:
            logger.error(f"Vector Search Failed: {e}")
            return []

        if not neighbors: return []
        
        result_candidates = neighbors[0] # List of Neighbor objects (id, distance)
        if not result_candidates: return []

        logger.info(f"🔍 [Retriever] Candidates for Rerank: {len(result_candidates)}")

        # 3.1 Buffer & Fetch Metadata
        # We need doc metadata to get SSOT score
        # Collect unique doc_ids first
        candidate_map = []
        unique_doc_ids = set()
        
        for match in result_candidates:
            if "::" not in match.id: continue
            doc_id, chunk_id = match.id.split("::")
            unique_doc_ids.add(doc_id)
            
            candidate_map.append({
                "match": match,
                "doc_id": doc_id,
                "chunk_id": chunk_id,
                "vector_score": match.distance if hasattr(match, 'distance') else 0.0
            })
            
        # Batch Fetch/Cache Metadata
        doc_meta_cache = {}
        for did in unique_doc_ids:
            meta = self.repo.get_document(did)
            if meta and meta.get("active", True): # Active check
                doc_meta_cache[did] = meta

        # 3.2 Calculate Final Score
        # Normalize vector scores (optional, but good for mixing)
        # Assuming distance is cosine similarity (0-1) or dot product. 
        # If distance, we use it directly.
        
        scored_candidates = []
        for item in candidate_map:
            doc_id = item["doc_id"]
            meta = doc_meta_cache.get(doc_id)
            
            if not meta: continue # Skip if metadata missing or inactive
            
            vec_score = item["vector_score"]
            ssot_score = meta.get("ssot_score", 50) # Default 50
            
            if RERANK_ENABLED:
                # Formula: Alpha * Vector + Beta * (SSOT/100)
                # Ensure SSOT is normalized 0-1
                final_score = (ALPHA * vec_score) + (BETA * (ssot_score / 100.0))
            else:
                final_score = vec_score

            item["final_score"] = final_score
            item["ssot_score"] = ssot_score
            item["ssot_explain"] = meta.get("ssot_explain", "")
            scored_candidates.append(item)
            
        # 3.3 Sort by Final Score
        scored_candidates.sort(key=lambda x: x["final_score"], reverse=True)
        
        # 4. Construct Evidence (with Top K & Diversity)
        final_chunks: List[Evidence] = []
        doc_counter = {}
        
        for item in scored_candidates:
            doc_id = item["doc_id"]
            chunk_id = item["chunk_id"]
            
            # Diversity Check
            if doc_counter.get(doc_id, 0) >= PER_DOC_CAP: continue
            
            # Fetch Content (Using existing GCS Logic)
            # Optimization: could cache GCS chunks per doc_id if multiple chunks from same doc
            meta = doc_meta_cache[doc_id]
            snippet, page_num = "", 1
            
            try:
                # Reuse _fetch_gcs_chunks logic (method below)
                # Ideally cache this too
                gcs_chunks = self._fetch_gcs_chunks(doc_id, meta)
                target = next((c for c in gcs_chunks if c.get("chunk_id") == chunk_id), None)
                if target:
                    snippet = target.get("text", "")
                    page_num = target.get("page", 1)
            except Exception as e:
                logger.warning(f"Content Fetch Fail: {e}")
                snippet = "Content load error"

            # Create Evidence with SSOT Extras
            evidence = Evidence(
                doc_id=doc_id,
                chunk_id=chunk_id,
                page=page_num,
                source_link=meta.get("source_link"),
                snippet=snippet[:500],
                title=meta.get("title", "Untitled"),
                # Extra fields will be handled by schema or ignored if strict
                # We will inject them into 'extra' if model supports, or assume model updated
            )
            # Monkey-patch or assume Evidence updated in Phase 4
            # Or use 'extra' dict if Pydantic model allows
            evidence.ssot_score = item["ssot_score"]
            evidence.ssot_explain = item["ssot_explain"]
            evidence.relevance = item["final_score"]
            
            final_chunks.append(evidence)
            doc_counter[doc_id] = doc_counter.get(doc_id, 0) + 1
            
            if len(final_chunks) >= top_k:
                break
                
        return final_chunks

    def _fetch_gcs_chunks(self, doc_id: str, doc_meta: Dict) -> List[Dict]:
        # Helper to fetch chunks from GCS
        try:
            # 1. Check if 'chunks' collection has GCS URI
            # (In-memory cache for repeated calls in same request recommended but omitting for safety)
            chunk_ref = self.repo.get_firestore_client().collection("chunks").document(doc_id).get()
            if not chunk_ref.exists: return []
            
            gcs_uri = chunk_ref.get("gcs_chunks_uri")
            if not gcs_uri: return []
            
            # 2. Download from GCS
            from google.cloud import storage
            storage_client = storage.Client(project=PROJECT_ID)
            
            parts = gcs_uri.replace("gs://", "").split("/", 1)
            bucket = storage_client.bucket(parts[0])
            blob = bucket.blob(parts[1])
            
            import json
            content = blob.download_as_text()
            return json.loads(content)
            
        except Exception as e:
            logger.error(f"GCS Fetch Exception: {e}")
            return []
