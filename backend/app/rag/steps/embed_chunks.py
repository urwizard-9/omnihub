import json
import logging
import time
import vertexai
from vertexai.language_models import TextEmbeddingModel
from google.cloud import storage
from google.cloud import firestore

# [통합] Backend Imports
from app.core.config import settings
from app.core.gcp_clients import get_firestore_client

# Logger
logger = logging.getLogger("ChunkEmbedder")
logger.setLevel(logging.INFO)

class ChunkEmbedder:
    def __init__(self):
        self.db = get_firestore_client()
        self.project_id = settings.PROJECT_ID
        self.location = getattr(settings, "VERTEX_LOCATION", "us-central1")
        self.bucket_name = getattr(settings, "GCS_BUCKET", f"{self.project_id}-docai-output")
        self.bucket = storage.Client(project=self.project_id).bucket(self.bucket_name)

        # Vertex Init
        vertexai.init(project=self.project_id, location=self.location)
        self.model_name = getattr(settings, "VERTEX_EMBED_MODEL", "text-embedding-004")
        self.model = TextEmbeddingModel.from_pretrained(self.model_name)
        self.batch_size = 20 # [Optimized] Increased from 5 to 20 for speed

    def embed_batch(self, texts):
        all_embeddings = []
        for i in range(0, len(texts), self.batch_size):
            batch = texts[i : i + self.batch_size]
            try:
                embeddings = self.model.get_embeddings(batch)
                all_embeddings.extend([e.values for e in embeddings])
            except Exception as e:
                logger.error(f"Embedding Batch Error: {e}")
                # For robustness, we might want to retry or skip. 
                # Here we re-raise to fail the doc safely.
                raise e
        return all_embeddings

    def load_json_from_gcs(self, gcs_uri: str):
        if not gcs_uri or not gcs_uri.startswith("gs://"): return None
        blob_path = gcs_uri.replace(f"gs://{self.bucket_name}/", "")
        blob = self.bucket.blob(blob_path)
        try:
            return json.loads(blob.download_as_text())
        except Exception:
            return None

    def _load_doc_entities(self, doc_id: str):
        """Phase B-2에서 추출한 Entity/Relation 로드"""
        try:
            ent_meta = self.db.collection("entities").document(doc_id).get()
            if not ent_meta.exists: return None
            
            gcs_uri = ent_meta.get("gcs_entities_uri")
            if not gcs_uri: return None
            
            return self.load_json_from_gcs(gcs_uri)
        except Exception as e:
            logger.warning(f"Failed to load entities for context injection: {e}")
            return None

    def _inject_context(self, chunk_text: str, chunk_id: str, entities_data: dict) -> str:
        """
        [Indexing-Time Augmentation]
        텍스트 뒤에 그래프 컨텍스트(관계/엔티티)를 주입하여 임베딩 품질 향상
        """
        if not entities_data: return chunk_text
        
        # 1. 해당 청크와 관련된 Relations 찾기
        relevant_rels = [
            r for r in entities_data.get("relations", []) 
            if r.get("evidence_chunk_id") == chunk_id
        ]
        
        # 2. 해당 청크와 관련된 Entities 찾기
        # evidence 리스트 중 chunk_id가 일치하는 것이 있는 엔티티
        relevant_ents = []
        for ent in entities_data.get("entities", []):
            for ev in ent.get("evidence", []):
                if ev.get("chunk_id") == chunk_id:
                    relevant_ents.append(ent)
                    break 
        
        if not relevant_rels and not relevant_ents:
            return chunk_text
            
        # 3. 컨텍스트 텍스트 구성
        context_lines = []
        
        # Relations: (Subj) --[Pred]--> (Obj)
        if relevant_rels:
            rel_strs = []
            for r in relevant_rels[:5]: # Top 5 only
                rel_strs.append(f"({r.get('src')}) --[{r.get('rel_type')}]--> ({r.get('dst')})")
            context_lines.append("* Relations: " + ", ".join(rel_strs))
            
        # Entities: Name (Type)
        if relevant_ents:
            ent_strs = []
            for e in relevant_ents[:10]: # Top 10 only
                ent_strs.append(f"{e.get('name')} ({e.get('type')})")
            context_lines.append("* Entities: " + ", ".join(ent_strs))
            
        context_str = "\n".join(context_lines)
        
        # 4. Injection
        # "Original Text \n\n [Graph Context] \n ..."
        return f"{chunk_text}\n\n[Graph Context]\n{context_str}"

    def process_single_document(self, doc_id: str):
        profile_ref = self.db.collection("profiles").document(doc_id).get()
        if not profile_ref.exists: return
        profile_data = profile_ref.to_dict()
        if not profile_data.get("active"): return

        logger.info(f"🧬 [Embed] 임베딩 시작: {doc_id}")

        chunks_meta = self.db.collection("chunks").document(doc_id).get()
        if not chunks_meta.exists: return
        
        chunks_data = self.load_json_from_gcs(chunks_meta.get("gcs_chunks_uri"))
        if not chunks_data: return
        
        chunks = chunks_data.get("chunks", []) if isinstance(chunks_data, dict) else chunks_data
        if not chunks: return
        
        # [Feature] Load Graph Data for Context Injection
        entities_data = self._load_doc_entities(doc_id)
        
        policy_data = self.db.collection("policies").document(doc_id).get()
        policy = policy_data.to_dict() if policy_data.exists else {}
        
        target_chunks = []
        texts_to_embed = []
        
        for c in chunks:
            chunk_text = c.get("text", "")
            if not chunk_text.strip(): continue
            
            chunk_id = c.get("chunk_id")
            
            # [Feature] Inject Graph Context before embedding
            augmented_text = self._inject_context(chunk_text, chunk_id, entities_data)
            
            meta = {
                "tenant_id": getattr(settings, "TENANT_ID", "default"),
                "engagement_id": getattr(settings, "ENGAGEMENT_ID", "default"),
                "doc_id": doc_id,
                "chunk_id": chunk_id,
                "doc_content_hash": profile_data.get("doc_content_hash"),
                "security_level": policy.get("security_level", "L1"),
                "ssot_level": policy.get("ssot_level", "Draft"),
                "page_no": c.get("page_start_no"),
                "source_uri": profile_data.get("gcs_uris", {}).get("raw_file"),
                "chunk_type": c.get("type", "text")
            }
            # Note: We embed augmented_text, but we might want to keep original text in metadata?
            # Or just rely on chunks collection for original text.
            target_chunks.append({"meta": meta, "text": chunk_text}) # Keep original for reference
            texts_to_embed.append(augmented_text) # Embed AUGMENTED text
            
        if not texts_to_embed: return
        
        vectors = self.embed_batch(texts_to_embed)
        
        embedded_result = []
        for item, vec in zip(target_chunks, vectors):
            embedded_result.append({
                "chunk_id": item["meta"]["chunk_id"],
                "vector": vec,
                "metadata": item["meta"]
            })
            
        # Save GCS
        content_hash = profile_data.get("doc_content_hash", "nohash")
        embed_path = f"embeddings/{doc_id}/{content_hash}/embeddings.json"
        
        payload = {
            "doc_id": doc_id,
            "embeddings": embedded_result,
            "count": len(embedded_result),
            "model_version": self.model_name,
            "created_at": time.time()
        }
        
        blob = self.bucket.blob(embed_path)
        blob.upload_from_string(json.dumps(payload, ensure_ascii=False), content_type="application/json")
        gcs_uri = f"gs://{self.bucket_name}/{embed_path}"
        
        # Firestore
        self.db.collection("embeddings").document(doc_id).set({
            "doc_id": doc_id,
            "gcs_embeddings_uri": gcs_uri,
            "count": len(embedded_result),
            "model_version": self.model_name,
            "updated_at": firestore.SERVER_TIMESTAMP
        }, merge=True)
        
        self.db.collection("profiles").document(doc_id).set({
            "process_flags": {"embed": False}
        }, merge=True)
        
        logger.info(f"✅ [Embed] 임베딩 완료: {len(embedded_result)} vectors (with Graph Context)")
