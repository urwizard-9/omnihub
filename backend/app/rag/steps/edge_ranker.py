import logging
import math
import time
import os
import re
from typing import List, Dict, Any
from google.cloud import firestore

from app.core.config import settings
from app.core.gcp_clients import get_firestore_client

logger = logging.getLogger("EdgeRanker")
logger.setLevel(logging.INFO)

class EdgeRanker:
    def __init__(self):
        self.db = get_firestore_client()
        
        # 1. Settings
        # Cap top concepts per doc to prevent graph explosion (default 15)
        self.per_doc_cap: int = int(getattr(settings, "PER_DOC_TOP_CONCEPTS", 15))
        self.ranker_version: str = getattr(settings, "EDGE_RANKER_VERSION", "v2-tfidf-penalty")
        self.min_rank_score: float = float(getattr(settings, "MIN_RANK_SCORE", 0.1))
        
        # Diversity & Weights
        self.max_per_concept_type: int = int(getattr(settings, "MAX_PER_CONCEPT_TYPE", 5))
        # Default Weights if not in settings
        default_weights = {"ORG": 1.2, "PERSON": 1.2, "GPE": 1.1, "EVENT": 1.3, "CONCEPT": 1.5, "OTHERS": 0.8}
        self.edge_type_weights: Dict[str, float] = getattr(settings, "EDGE_TYPE_WEIGHTS", default_weights)

        # Load Stopwords for Penalty
        self.stopwords = set()
        stopwords_file = os.path.join("app", "rag", "rules", "stopwords.txt")
        if os.path.exists(stopwords_file):
            try:
                with open(stopwords_file, "r", encoding="utf-8") as f:
                    self.stopwords = {line.strip() for line in f if line.strip()}
                logger.info(f"Loaded {len(self.stopwords)} stopwords for Penalty")
            except Exception as e:
                logger.warning(f"Failed to load stopwords: {e}")

        # Simple In-Memory Cache for N (Total Docs)
        self.cached_n = None
        self.last_n_update = 0

    def _get_total_docs_count(self, tenant_id: str, engagement_id: str) -> int:
        """
        Estimate Total Documents (N) for IDF Calculation.
        Cache for 5 minutes.
        """
        now = time.time()
        if self.cached_n is not None and (now - self.last_n_update) < 300:
            return self.cached_n

        try:
            # Count active profiles (approx)
            # Using count aggregations would be better, but for now simple query
            # or keep a stats document. Here we do a count query with limit to avoid full scan cost if huge.
            # Actually, Firestore count query is cheap.
            query = (self.db.collection("profiles")
                     .where(filter=firestore.FieldFilter("tenant_id", "==", tenant_id))
                     .where(filter=firestore.FieldFilter("engagement_id", "==", engagement_id))
                     .where(filter=firestore.FieldFilter("active", "==", True))
                     .count())
            
            results = query.get()
            count = int(results[0][0].value)
            
            # Avoid Zero Division
            if count < 1: count = 1
            
            self.cached_n = count
            self.last_n_update = now
            logger.info(f"📊 [Ranker] Total Docs Estimate (N): {count}")
            return count
        except Exception as e:
            logger.warning(f"Failed to count docs: {e}")
            return 100 # Fallback

    def load_concept_df(self, concept_ids: List[str], tenant_id: str, engagement_id: str) -> Dict[str, int]:
        """
        Fetch Document Frequency (DF) for concepts.
        Priority:
        1. graph_serving_concepts/{concept_id}.doc_count (Serving Layer - Fastest)
        2. concepts/{concept_id}.doc_count (Base Layer - Fallback)
        3. Default 1
        """
        if not concept_ids: return {}
        
        unique_ids = list(set(concept_ids))
        df_map = {}
        
        # Batch max 30
        chunk_size = 30
        chunks = [unique_ids[i:i + chunk_size] for i in range(0, len(unique_ids), chunk_size)]
        
        for chunk in chunks:
            # Try Serving Layer First (It has pre-aggregated stats usually)
            # But wait, serving layer might not be built yet.
            # Let's stick to 'concepts' collection which is built in Step 3.
            # Building stats might be in 'concepts' or 'concept_stats'.
            # Assuming 'concepts' doc has 'doc_frequency' or 'mentions' count.
            # If not, we default to 1.
            
            # Actually, BuildConcepts step should have updated 'doc_count' in concepts.
            # Let's check concepts collection.
            
            refs = [self.db.collection("concepts").document(cid) for cid in chunk]
            docs = self.db.get_all(refs)
            
            for doc in docs:
                cid = doc.id
                if doc.exists:
                    data = doc.to_dict()
                    # Priority check for DF fields
                    # 1. doc_count (Active docs count)
                    # 2. mentions (Total mentions, proxy for DF)
                    df = data.get("doc_count", data.get("mentions", 1))
                    if df < 1: df = 1
                    df_map[cid] = df
                else:
                    df_map[cid] = 1 # Default
                    
        return df_map

    def _fetch_concept_metadata(self, concept_ids: List[str]) -> Dict[str, Dict[str, Any]]:
        """
        Fetch concept metadata (DF, Type, Name) in batches (max 10)
        """
        if not concept_ids: return {}
        
        unique_ids = list(set(concept_ids))
        meta_map = {}
        
        # Batch max 10 for getAll (Firestore limit) - actually getAll supports more but let's be safe
        # Google Firestore Python Client getAll supports list of keys.
        
        chunk_size = 30 # Python client can handle more, but let's chunk.
        chunks = [unique_ids[i:i + chunk_size] for i in range(0, len(unique_ids), chunk_size)]
        
        for chunk in chunks:
            refs = [self.db.collection("concepts").document(cid) for cid in chunk]
            docs = self.db.get_all(refs)
            
            for doc in docs:
                if doc.exists:
                    meta_map[doc.id] = doc.to_dict()
                else:
                    meta_map[doc.id] = {} # Empty if not found
                    
        return meta_map

    def calculate_score(self, edge: Dict, concept: Dict, N: int) -> tuple:
        """
        Calculate Explainable Rank Score with Penalties for Stopwords/Dates
        Returns: (score, features_dict)
        """
        # Features
        confidence = float(edge.get("confidence", 1.0))
        mentions = int(edge.get("mentions_count", 1))
        
        df = int(concept.get("doc_frequency", 1))
        concept_type = concept.get("type", "OTHERS")
        concept_name = concept.get("canonical_name", concept.get("name", "")).strip()
        
        # 1. TF (Log scaled)
        tf = math.log(1 + mentions)
        
        # 2. IDF
        # Standard IDF: log(N / (df + 1)) + 1
        idf = math.log((N + 1) / (df + 1)) + 1.0
        
        # [NEW] Penalty Logic
        is_penalized = False
        penalty_reason = ""

        # A. Stopwords Penalty
        if concept_name in self.stopwords:
            idf = 0.05 # Severe penalty
            is_penalized = True
            penalty_reason = "stopword"
        
        # B. Length Penalty (1 char)
        elif len(concept_name) < 2:
             idf = 0.05
             is_penalized = True
             penalty_reason = "too_short"

        # C. Date/Number Pattern Penalty
        else:
             if re.match(r'^\d{4}년$', concept_name) or re.match(r'^\d+[월일]$', concept_name):
                 idf = 0.1 # Moderate penalty for dates
                 is_penalized = True
                 penalty_reason = "date_pattern"
             elif re.match(r'^[0-9]+$', concept_name):
                 idf = 0.05
                 is_penalized = True
                 penalty_reason = "numeric_only"

        if not is_penalized and idf < 0.1: 
            idf = 0.1 # Min floor for normal terms
        
        # 3. Weights
        type_weight = self.edge_type_weights.get(concept_type, 1.0)
        
        # Final Score
        # score = confidence * TF * IDF * Weight
        raw_score = confidence * tf * idf * type_weight
        
        features = {
            "confidence": round(confidence, 2),
            "mentions": mentions,
            "tf": round(tf, 2),
            "df": df,
            "idf": round(idf, 2),
            "type_weight": type_weight,
            "is_penalized": is_penalized,
            "penalty_reason": penalty_reason
        }
        
        return round(raw_score, 4), features

    def process_single_document(self, doc_id: str):
        # 1. Fetch Edges with Scope Filters
        # First, we need tenant/engagement to apply filters. 
        # But usually edge_id is usually enough? No, we should be strict.
        # Let's read doc profile first to get scope.
        profile_ref = self.db.collection("profiles").document(doc_id).get()
        if not profile_ref.exists:
            logger.warning(f"SKIP Edges {doc_id}: Profile not found")
            return
            
        profile = profile_ref.to_dict()
        tenant_id = profile.get("tenant_id")
        engagement_id = profile.get("engagement_id")
        
        if not tenant_id or not engagement_id:
             logger.warning(f"SKIP Edges {doc_id}: Missing scope (tenant/engagement)")
             return

        # 1. Fetch Edges with Scope Filters (Strict)
        query = (self.db.collection("edges_doc_concept")
            .where(filter=firestore.FieldFilter("doc_id", "==", doc_id))
            .where(filter=firestore.FieldFilter("tenant_id", "==", tenant_id))
            .where(filter=firestore.FieldFilter("engagement_id", "==", engagement_id))
            .where(filter=firestore.FieldFilter("active", "==", True)))
            
        edges_ref = query.stream()
        
        edges = []
        concept_ids = []
        for e in edges_ref:
            d = e.to_dict()
            d["_ref"] = e.reference
            edges.append(d)
            if d.get("concept_id"):
                concept_ids.append(d.get("concept_id"))
        
        if not edges: 
            logger.info(f"No edges found for {doc_id}")
            return

        # 2. Fetch Concept Metadata & Stats (DF)
        N = self._get_total_docs_count(tenant_id, engagement_id)
        
        # Use new load_concept_df for DF stats
        df_map = self.load_concept_df(concept_ids, tenant_id, engagement_id)
        # Fetch meta for Type/Name
        concept_meta_map = self._fetch_concept_metadata(concept_ids)
        
        # Merge DF into meta
        for cid, meta in concept_meta_map.items():
            meta["doc_frequency"] = df_map.get(cid, 1)
        
        # 3. Score Edges
        scored_edges = []
        for edge in edges:
            cid = edge.get("concept_id")
            concept = concept_meta_map.get(cid, {})
            
            score, features = self.calculate_score(edge, concept, N)
            
            edge["rank_score"] = score
            edge["rank_features"] = features
            
            # Enrich for diversity check
            edge["_concept_type"] = concept.get("type", "OTHERS")
            edge["_concept_name"] = concept.get("canonical_name", "Unknown")
            
            scored_edges.append(edge)
            
        # 4. Diversity Sort & Top-K
        # Sort by Score Desc
        scored_edges.sort(key=lambda x: x["rank_score"], reverse=True)
        
        final_top_k = []
        seen_concepts = set()
        type_counts = {}
        
        for edge in scored_edges:
            # a. Check Min Score
            if edge["rank_score"] < self.min_rank_score:
                continue
                
            cid = edge["concept_id"]
            ctype = edge["_concept_type"]
            
            # b. Check Duplicate Concept (Same doc shouldn't have multple edges to same concept usually, but safety)
            if cid in seen_concepts:
                continue
                
            # c. Check Type Cap
            current_type_count = type_counts.get(ctype, 0)
            if current_type_count >= self.max_per_concept_type:
                continue
            
            # Accept
            final_top_k.append(edge)
            seen_concepts.add(cid)
            type_counts[ctype] = current_type_count + 1
            
            if len(final_top_k) >= self.per_doc_cap:
                break
                
        # 5. Batch Update
        batch = self.db.batch()
        batch_cnt = 0
        
        # Update All Edges (with score) or Just Top K?
        # Ideally update all edges with their scores for future queries.
        # But for write cost optimization, maybe only top-k? 
        # No, update ALL scored edges is better for consistency.
        # Let's update ALL edges that we calculated.
        
        for edge in scored_edges:
            update_data = {
                "rank_score": edge["rank_score"],
                "rank_features": edge["rank_features"],
                "ranker_version": self.ranker_version,
                "scored_at": firestore.SERVER_TIMESTAMP
            }
            batch.update(edge["_ref"], update_data)
            batch_cnt += 1
            if batch_cnt >= 400:
                batch.commit()
                batch = self.db.batch()
                batch_cnt = 0
        
        # Update Doc Top Concepts
        top_concepts_data = [{
            "concept_id": e["concept_id"],
            "score": e["rank_score"],
            "mentions": e.get("mentions_count", 0),
            "edge_type": e.get("edge_type", "mentions"),
            "concept_type": e["_concept_type"],
            "concept_name": e["_concept_name"]
        } for e in final_top_k]
        
        batch.set(self.db.collection("documents").document(doc_id), {
            "top_concepts": top_concepts_data,
            "top_concepts_updated_at": firestore.SERVER_TIMESTAMP
        }, merge=True)
        
        # Finish last batch
        if batch_cnt > 0 or len(final_top_k) > 0: # Ensure doc update is committed
            batch.commit()
            
        logger.info(f"✅ [Rank] {doc_id} complete. Top {len(final_top_k)} selected from {len(scored_edges)} edges.")
