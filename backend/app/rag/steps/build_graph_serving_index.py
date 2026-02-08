import logging
from collections import defaultdict
from typing import Dict, Any, List
import itertools
import hashlib
import re
from google.cloud import firestore

# [통합] Backend Imports
from app.core.config import settings
from app.core.gcp_clients import get_firestore_client
from app.common.enums import ReviewStatus

# Logger
logger = logging.getLogger("GraphServingBuilder")
logger.setLevel(logging.INFO)

class GraphServingIndexBuilder:
    def __init__(self):
        self.db = get_firestore_client()
        
        # 1. Scope Settings
        self.tenant_id = getattr(settings, "TENANT_ID", "default")
        self.engagement_id = getattr(settings, "ENGAGEMENT_ID", "default")
        self.serving_version = getattr(settings, "GRAPH_SERVING_INDEX_VERSION", "v2-ranked")
        # Lower cap to prevent initial load overload (Default 20)
        self.per_node_cap = int(getattr(settings, "GRAPH_SERVING_CAP", 20))
        
        # Review Filter (Configurable)
        # Default: ["APPROVED"] for strict production, ["APPROVED", "PENDING"] for dev
        default_statuses = "APPROVED"
        status_str = getattr(settings, "GRAPH_SERVING_ALLOWED_STATUSES", default_statuses)
        self.allowed_statuses = [s.strip() for s in status_str.split(",")]
        
        # Co-occurrence Settings
        self.cooc_doc_topk = int(getattr(settings, "COOC_DOC_TOPK", 10))
        self.cooc_min_shared = int(getattr(settings, "COOC_MIN_SHARED_DOCS", 2))
        self.cooc_min_weight = float(getattr(settings, "COOC_MIN_WEIGHT", 0.8)) # Default: 0.8
        self.cooc_neighbor_cap = int(getattr(settings, "COOC_NEIGHBOR_CAP", 4)) # Default: 4 (Sparse)

        # In-Memory Cache (For Batch Build)
        self.doc_meta = {} # doc_id -> {title, path, ...}
        self.concept_meta = {} # concept_id -> {name, type}

    def _get_doc_title(self, doc_data: dict, profile_data: dict = None) -> str:
        """
        Title Fallback Policy:
        1. documents.title
        2. profiles.title (if available)
        3. doc_id
        """
        if doc_data.get("title"):
            return doc_data.get("title")
        
        if profile_data and profile_data.get("title"):
            return profile_data.get("title")
            
        return doc_data.get("id", "Untitled")

    def _normalize_name(self, name: str) -> str:
        if not name: return ""
        norm = name.lower().strip()
        norm = re.sub(r'[^\w\s]', '', norm) 
        norm = re.sub(r'\s+', ' ', norm)
        return norm.strip()

    def _generate_concept_id(self, name: str) -> str:
        norm = self._normalize_name(name)
        return hashlib.md5(norm.encode()).hexdigest()

    def run(self):
        """
        Full Batch Build
        1. Load Valid Docs & Meta
        2. Load Concepts Meta
        3. Aggregate Explicit Relations (Semantic) [NEW]
        4. Aggregate Co-occurrence (Statistical)
        5. Write to Serving Index
        """
        logger.info("🚀 [GraphServing] Starting Full Build...")
        
        # 1. Load Docs
        docs_ref = (self.db.collection("documents")
            .where(filter=firestore.FieldFilter("tenant_id", "==", self.tenant_id))
            .where(filter=firestore.FieldFilter("engagement_id", "==", self.engagement_id))
            .where(filter=firestore.FieldFilter("active", "==", True))
            .stream())
            
        valid_doc_ids = set()
        for d in docs_ref:
            data = d.to_dict()
            status = data.get("review_status")
            if status not in self.allowed_statuses:
                continue
            
            valid_doc_ids.add(d.id)
            self.doc_meta[d.id] = {
                "title": data.get("title", d.id), # Fallback
                "path": data.get("file_path", ""), # Virtual path for UI grouping
                "top_concepts": data.get("top_concepts", []) # Use pre-computed ranker results
            }
            
        logger.info(f"loaded {len(valid_doc_ids)} valid docs (Status: {self.allowed_statuses})")
        
        # 2. Load Concepts Meta
        concepts_ref = (self.db.collection("concepts")
            .where(filter=firestore.FieldFilter("tenant_id", "==", self.tenant_id))
            .where(filter=firestore.FieldFilter("engagement_id", "==", self.engagement_id))
            .where(filter=firestore.FieldFilter("active", "==", True))
            .stream())
            
        for c in concepts_ref:
            d = c.to_dict()
            self.concept_meta[c.id] = {
                "name": d.get("canonical_name", c.id),
                "type": d.get("type", "OTHERS")
            }
            
        # Shared Pair Stats (Key: (id1, id2))
        pair_stats = defaultdict(lambda: {"weight": 0.0, "shared": 0, "rel_types": set()})

        # 3. Aggregate Explicit Relations
        logger.info("Computing Explicit Relations...")
        entities_ref = (self.db.collection("entities")
             # Ideally filter by doc scope if possible, but doc_id is in ID.
             # We iterate all and check valid_doc_ids.
             .stream())
             
        # Optimization: Fetch only docs in valid_doc_ids? keys are doc_ids. Correct.
        # But stream() scans all. Maybe iterate valid_doc_ids and fetch entities?
        # If too many docs, batch get is better.
        # Let's iterate valid_doc_ids in batches.
        
        chunk_size = 100
        doc_id_list = list(valid_doc_ids)
        chunks = [doc_id_list[i:i + chunk_size] for i in range(0, len(doc_id_list), chunk_size)]
        
        for chunk in chunks:
            refs = [self.db.collection("entities").document(did) for did in chunk]
            try:
                ent_docs = self.db.get_all(refs)
                for ed in ent_docs:
                    if not ed.exists: continue
                    data = ed.to_dict()
                    relations = data.get("relations", [])
                    
                    for rel in relations:
                        src = rel.get("src")
                        dst = rel.get("dst")
                        rtype = rel.get("rel_type")
                        
                        if not src or not dst: continue
                        
                        # Resolve IDs
                        # Note: We assume Concepts are already built for these names.
                        # If extraction found relation but concept wasn't built (e.g. filtered), we skip.
                        
                        sid = self._generate_concept_id(src)
                        did = self._generate_concept_id(dst)
                        
                        if sid not in self.concept_meta or did not in self.concept_meta:
                            continue
                            
                        # Canonical Order
                        if sid > did: sid, did = did, sid
                        k = (sid, did)
                        
                        pair_stats[k]["weight"] += 3.0 # Strong Weight for Explicit Relation
                        pair_stats[k]["shared"] += 1 # Count as shared context
                        if rtype:
                            pair_stats[k]["rel_types"].add(rtype)
            except Exception as e:
                logger.warning(f"Error fetching entities batch: {e}")

        # 4. Aggregate Doc-Concept Edges (for Co-occurrence)
        doc_neighbors = defaultdict(list) # For Co-occurrence Calc & Indexes
        concept_neighbors = defaultdict(list) # For Concept Index
        
        edges_ref = (self.db.collection("edges_doc_concept")
            .where(filter=firestore.FieldFilter("tenant_id", "==", self.tenant_id))
            .where(filter=firestore.FieldFilter("engagement_id", "==", self.engagement_id))
            .where(filter=firestore.FieldFilter("active", "==", True))
            .stream())
            
        for e in edges_ref:
            data = e.to_dict()
            doc_id = data.get("doc_id")
            concept_id = data.get("concept_id")
            
            if doc_id not in valid_doc_ids: continue
            if concept_id not in self.concept_meta: continue
            
            # Score Priority: rank_score > confidence
            score = data.get("rank_score")
            if score is None: 
                score = data.get("confidence", 1.0) * 0.5 # Penalty if no rank
            
            mentions = data.get("mentions_count", 0)
            
            # Data for Doc Index (Concepts)
            doc_neighbors[doc_id].append({
                "concept_id": concept_id,
                "name": self.concept_meta[concept_id]["name"],
                "type": self.concept_meta[concept_id]["type"],
                "score": score,
                "mentions": mentions
            })
            
            # Data for Concept Index (Docs)
            doc_info = self.doc_meta[doc_id]
            concept_neighbors[concept_id].append({
                "doc_id": doc_id,
                "title": doc_info["title"],
                "path": doc_info["path"],
                "score": score,
                "mentions": mentions
            })
 
        # 5. Concept Co-occurrence Calculation
        logger.info("Computing Co-occurrence...")
        
        # doc_neighbors map: doc_id -> list of {concept_id, score, ...}
        for doc_id, concepts in doc_neighbors.items():
            # 1. Filter Top-K Concepts (to avoid explosion like N*N for long docs)
            # Sort by score desc
            active_concepts = sorted(concepts, key=lambda x: x["score"], reverse=True)[:self.cooc_doc_topk]
            
            if len(active_concepts) < 2: continue
            
            # 2. Generate Pairs
            ids_scores = [(c["concept_id"], c["score"]) for c in active_concepts]
            # Combinations
            for (c1, s1), (c2, s2) in itertools.combinations(ids_scores, 2):
                # Canonical Order to avoid duplicates (A,B) vs (B,A)
                if c1 > c2: c1, c2 = c2, c1
                
                # Weight Strategy: Min or Product? 
                w = min(s1, s2)
                
                k = (c1, c2)
                pair_stats[k]["weight"] += w
                pair_stats[k]["shared"] += 1
                
        logger.info(f"Generated {len(pair_stats)} total pairs (Explicit + Cooc). Filtering...")
        
        # Pruning & Formatting Adjacency List
        concept_cooc_adj = defaultdict(list)
        
        for (c1, c2), stats in pair_stats.items():
            # If explicit relation exists, keep regardless of shared count (weight is high)
            is_explicit = len(stats["rel_types"]) > 0
            
            if not is_explicit and (stats["shared"] < self.cooc_min_shared or stats["weight"] < self.cooc_min_weight):
                continue
                
            # Add undirected edges (bi-directional)
            base_edge = {
                "weight": stats["weight"],
                "shared_docs": stats["shared"],
                "rel_types": list(stats["rel_types"]) if stats["rel_types"] else []
            }
            
            concept_cooc_adj[c1].append({**base_edge, "concept_id": c2})
            concept_cooc_adj[c2].append({**base_edge, "concept_id": c1})
            
        logger.info(f"Graph Edges ready for {len(concept_cooc_adj)} concepts.")
            
        # 6. Write Batches
        batch = self.db.batch()
        count = 0
        
        # Doc-Centric
        for doc_id in valid_doc_ids:
            # Use Ranker Result if available and better?
            # Existing aggregator logic re-calculates from edges.
            # But documents.top_concepts is "Single Source of Truth" for Doc-Concept.
            # Let's prefer 'documents.top_concepts' for Doc-Serving if available.
            
            pre_computed_top = self.doc_meta[doc_id].get("top_concepts")
            final_top_k = []
            
            if pre_computed_top:
                # Format: {concept_id, score, mentions, ...}
                final_top_k = pre_computed_top # Already sorted/capped by Ranker
            else:
                # Fallback to aggregation
                neighbors = doc_neighbors.get(doc_id, [])
                neighbors.sort(key=lambda x: x["score"], reverse=True)
                final_top_k = neighbors[:self.per_node_cap]
            
            payload = {
                "doc_id": doc_id,
                "title": self.doc_meta[doc_id]["title"],
                "path": self.doc_meta[doc_id]["path"],
                "tenant_id": self.tenant_id,
                "engagement_id": self.engagement_id,
                "top_concepts": final_top_k,
                "concept_count": len(doc_neighbors.get(doc_id, [])),
                "version": self.serving_version,
                "updated_at": firestore.SERVER_TIMESTAMP
            }
            batch.set(self.db.collection("graph_serving_docs").document(doc_id), payload, merge=True)
            count += 1
            if count >= 400:
                batch.commit()
                batch = self.db.batch()
                count = 0
                
        # Concept-Centric
        for concept_id, neighbors in concept_neighbors.items():
            neighbors.sort(key=lambda x: x["score"], reverse=True)
            top_k = neighbors[:self.per_node_cap]
            
            # Hybrid Neighbors (Cooc + Explicit)
            cooc_list = concept_cooc_adj.get(concept_id, [])
            cooc_list.sort(key=lambda x: x["weight"], reverse=True)
            cooc_top_k = cooc_list[:self.cooc_neighbor_cap]
            
            payload = {
                "concept_id": concept_id,
                "meta": self.concept_meta[concept_id],
                "tenant_id": self.tenant_id,
                "engagement_id": self.engagement_id,
                "top_docs": top_k,
                "neighbors": cooc_top_k, 
                "doc_count": len(neighbors),
                "version": self.serving_version,
                "updated_at": firestore.SERVER_TIMESTAMP
            }
            batch.set(self.db.collection("graph_serving_concepts").document(concept_id), payload, merge=True)
            count += 1
            if count >= 400:
                batch.commit()
                batch = self.db.batch()
                count = 0
                
        if count > 0: batch.commit()
        logger.info("✅ [GraphServing] Full Build Complete.")


    def process_single_document(self, doc_id: str):
        """
        Incremental Update for Single Document
        """
        logger.info(f"🔄 [GraphServing] Incremental: {doc_id}")
        
        # 1. Fetch Doc & Profile (For Title/Scope)
        doc_ref = self.db.collection("documents").document(doc_id).get()
        if not doc_ref.exists: return
        doc_data = doc_ref.to_dict()
        
        # Check Scope
        if doc_data.get("tenant_id") != self.tenant_id or doc_data.get("engagement_id") != self.engagement_id:
            logger.warning(f"SKIP {doc_id}: Scope Mismatch")
            return
            
        profile_ref = self.db.collection("profiles").document(doc_id).get()
        profile_data = profile_ref.to_dict() if profile_ref.exists else {}
            
        doc_title = self._get_doc_title(doc_data, profile_data)
        
        # 2. Update Doc-Centric Index
        # Prefer pre-computed top_concepts from Ranker
        top_concepts = doc_data.get("top_concepts", [])
        
        # If no top_concepts (Ranker didn't run?), fetch edges directly
        if not top_concepts:
            edges = (self.db.collection("edges_doc_concept")
                .where(filter=firestore.FieldFilter("doc_id", "==", doc_id))
                .where(filter=firestore.FieldFilter("active", "==", True))
                .stream())
            temp_list = []
            for e in edges:
                d = e.to_dict()
                score = d.get("rank_score", d.get("confidence", 0.5))
                # Need concept meta... fetch one by one is slow but OK for single doc fallback
                c_ref = self.db.collection("concepts").document(d["concept_id"]).get()
                c_name = c_ref.get("canonical_name") if c_ref.exists else "Unknown"
                temp_list.append({
                    "concept_id": d["concept_id"],
                    "name": c_name,
                    "score": score
                })
            temp_list.sort(key=lambda x: x["score"], reverse=True)
            top_concepts = temp_list[:self.per_node_cap]
            
        doc_payload = {
            "doc_id": doc_id,
            "title": doc_title,
            "tenant_id": self.tenant_id,
            "engagement_id": self.engagement_id,
            "top_concepts": top_concepts,
            "version": self.serving_version,
            "updated_at": firestore.SERVER_TIMESTAMP
        }
        self.db.collection("graph_serving_docs").document(doc_id).set(doc_payload, merge=True)
        
        # 3. Update Concept-Centric Index (Affected Concepts)
        affected_concepts = set(c["concept_id"] for c in top_concepts)
        
        batch = self.db.batch()
        count = 0
        
        for cid in affected_concepts:
            # Re-query Top Docs for this Concept (Scoped)
            # This is "Fan-In" query: Find all edges pointing to this concept
            c_edges = (self.db.collection("edges_doc_concept")
                .where(filter=firestore.FieldFilter("concept_id", "==", cid))
                .where(filter=firestore.FieldFilter("tenant_id", "==", self.tenant_id))
                .where(filter=firestore.FieldFilter("engagement_id", "==", self.engagement_id))
                .where(filter=firestore.FieldFilter("active", "==", True))
                .limit(self.per_node_cap * 2) # Optimize read: just get enough candidates
                # Ideally order by rank_score desc, but need composite index. 
                # If no index, fetch more and sort in memory.
                .stream())
                
            doc_candidates = []
            for edge in c_edges:
                ed = edge.to_dict()
                d_id = ed.get("doc_id")
                score = ed.get("rank_score", ed.get("confidence", 0.5))
                mentions = ed.get("mentions_count", 1)
                
                # We need doc title for serving. Fetch from serving index or doc?
                # Fetching N docs is expensive. Use lazy or just ID if fallback.
                # Optimization: Try to get title from doc meta cache if we had it, but this is incremental.
                # Let's peek into graph_serving_docs for title (it's fast read).
                serving_doc = self.db.collection("graph_serving_docs").document(d_id).get()
                title = serving_doc.get("title") if serving_doc.exists else d_id
                
                doc_candidates.append({
                    "doc_id": d_id,
                    "title": title,
                    "score": score,
                    "mentions": mentions
                })
            
            doc_candidates.sort(key=lambda x: x["score"], reverse=True)
            final_top_docs = doc_candidates[:self.per_node_cap]
            
            # Concept Meta (Light read)
            c_ref = self.db.collection("concepts").document(cid).get()
            c_meta = {"name": "", "type": ""}
            if c_ref.exists:
                d = c_ref.to_dict()
                c_meta = {"name": d.get("canonical_name"), "type": d.get("type")}
            
            c_payload = {
                "concept_id": cid,
                "meta": c_meta,
                "tenant_id": self.tenant_id,
                "engagement_id": self.engagement_id,
                "top_docs": final_top_docs,
                "doc_count": len(doc_candidates), # Approximate from limit query
                "version": self.serving_version,
                "updated_at": firestore.SERVER_TIMESTAMP
            }
            batch.set(self.db.collection("graph_serving_concepts").document(cid), c_payload, merge=True)
            count += 1
            if count >= 400:
                batch.commit()
                batch = self.db.batch()
                count = 0
                
        if count > 0: batch.commit()
        logger.info(f"✅ [GraphServing] Incremental Done. Updated {len(affected_concepts)} concepts.")

if __name__ == "__main__":
    builder = GraphServingIndexBuilder()
    builder.run()
