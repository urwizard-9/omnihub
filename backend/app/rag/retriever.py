import os
from dotenv import load_dotenv
load_dotenv()
import logging
from typing import List, Any, Dict, Optional
from pydantic import BaseModel
from google.cloud import aiplatform
# Import Namespace correctly
from google.cloud.aiplatform.matching_engine.matching_engine_index_endpoint import Namespace
from vertexai.language_models import TextEmbeddingModel 
from app.services.firestore_repo import FirestoreRepo
from app.common.schemas import Evidence

logger = logging.getLogger("Retriever")

# --- Env Config ---
PROJECT_ID = os.getenv("GCP_PROJECT_ID")
LOCATION = os.getenv("VERTEX_LOCATION", "us-central1")
INDEX_ENDPOINT_NAME = os.getenv("VECTOR_INDEX_ENDPOINT")
DEPLOYED_INDEX_ID = os.getenv("VECTOR_DEPLOYED_INDEX_ID")
EMBED_MODEL_NAME = os.getenv("VERTEX_EMBED_MODEL", "text-embedding-004")

# Tuning Params
TOPK_MULT = int(os.getenv("RETRIEVER_TOPK_MULT", 10)) 
PER_DOC_CAP = int(os.getenv("PER_DOC_CHUNK_CAP", 3))

class RetrievedChunk(BaseModel):
    doc_id: str
    chunk_id: str
    score: float
    text: str 
    page: Optional[int] = 1
    doc_title: Optional[str] = None
    source_link: Optional[str] = None
    security_level: Optional[str] = None
    
class Retriever:
    def __init__(self, repo: FirestoreRepo):
        self.repo = repo
        
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
        Main Retrieval Pipeline with SSOT Reranking and Tenant Isolation
        """
        RERANK_ENABLED = os.getenv("SSOT_RERANK_ENABLED", "true").lower() == "true"
        ALPHA = float(os.getenv("SSOT_RERANK_ALPHA", 0.85))
        BETA = float(os.getenv("SSOT_RERANK_BETA", 0.15))

        # 1. Embed
        query_vec = self._embed_query(query)
        
        # 2. Build Filter (Tenant Isolation)
        restricts = []
        tenant_id = os.getenv("TENANT_ID")
        
        if tenant_id:
            # Must match the namespace used in upsert_vector_index.py (VectorSchema.TENANT_ID="tenant_id")
            restricts.append(Namespace("tenant_id", [tenant_id]))
            logger.info(f"🔎 Filter applied: tenant_id='{tenant_id}'")
        
        # 3. Search 
        search_k = top_k * TOPK_MULT
        
        try:
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
        
        result_candidates = neighbors[0] 
        if not result_candidates: return []

        logger.info(f"🔍 [Retriever] Candidates for Rerank: {len(result_candidates)}")

        # 3.1 Buffer & Fetch Metadata
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
            
        doc_meta_cache = {}
        for did in unique_doc_ids:
            meta = self.repo.get_document(did)
            if meta and meta.get("active", True): 
                doc_meta_cache[did] = meta

        # 3.2 Calculate Final Score
        scored_candidates = []
        for item in candidate_map:
            doc_id = item["doc_id"]
            meta = doc_meta_cache.get(doc_id)
            
            if not meta: continue 
            
            vec_score = item["vector_score"]
            ssot_score = meta.get("ssot_score", 50) 
            
            if RERANK_ENABLED:
                final_score = (ALPHA * vec_score) + (BETA * (ssot_score / 100.0))
            else:
                final_score = vec_score

            item["final_score"] = final_score
            item["ssot_score"] = ssot_score
            item["ssot_explain"] = meta.get("ssot_explain", "")
            scored_candidates.append(item)
            
        # 3.3 Sort
        scored_candidates.sort(key=lambda x: x["final_score"], reverse=True)
        
        # 4. Construct Evidence
        final_chunks: List[Evidence] = []
        doc_counter = {}
        
        for item in scored_candidates:
            doc_id = item["doc_id"]
            chunk_id = item["chunk_id"]
            
            if doc_counter.get(doc_id, 0) >= PER_DOC_CAP: continue
            
            meta = doc_meta_cache[doc_id]
            snippet, page_num = "", 1
            
            try:
                gcs_chunks = self._fetch_gcs_chunks(doc_id, meta)
                target = next((c for c in gcs_chunks if str(c.get("chunk_id")) == str(chunk_id)), None)
                if target:
                    snippet = target.get("text", "")
                    page_num = target.get("page_start_no") or target.get("page", 1)
            except Exception as e:
                logger.warning(f"Content Fetch Fail: {e}")
                snippet = "Content load error"

            evidence = Evidence(
                doc_id=doc_id,
                chunk_id=chunk_id,
                page=page_num,
                source_link=meta.get("source_link"),
                snippet=snippet[:1500],
                title=meta.get("title", "Untitled"),
            )
            evidence.ssot_score = item["ssot_score"]
            evidence.ssot_explain = item["ssot_explain"]
            evidence.relevance = item["final_score"]
            
            final_chunks.append(evidence)
            doc_counter[doc_id] = doc_counter.get(doc_id, 0) + 1
            
            if len(final_chunks) >= top_k:
                break
                
        return final_chunks

    def _fetch_gcs_chunks(self, doc_id: str, doc_meta: Dict) -> List[Dict]:
        try:
            chunk_ref = self.repo.get_firestore_client().collection("chunks").document(doc_id).get()
            if not chunk_ref.exists: return []
            
            gcs_uri = chunk_ref.get("gcs_chunks_uri")
            if not gcs_uri: return []
            
            from google.cloud import storage
            storage_client = storage.Client(project=PROJECT_ID)
            
            parts = gcs_uri.replace("gs://", "").split("/", 1)
            bucket = storage_client.bucket(parts[0])
            blob = bucket.blob(parts[1])
            
            import json
            content = blob.download_as_text()
            data = json.loads(content)
            
            # [Fix] JSON structure handling
            if isinstance(data, dict):
                return data.get("chunks", [])
            return data
            
        except Exception as e:
            logger.error(f"GCS Fetch Exception: {e}")
            return []