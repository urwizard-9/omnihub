import logging
import os
from typing import Dict, Any, List, Tuple
from app.services.firestore_repo import FirestoreRepo

# 환경 변수 로드 (일부 설정용)
GRAPH_INIT_MAX_NODES = int(os.getenv("GRAPH_INIT_MAX_NODES", 300))
GRAPH_INIT_MAX_EDGES = int(os.getenv("GRAPH_INIT_MAX_EDGES", 500))

logger = logging.getLogger("GraphQueryService")

class GraphQueryService:
    def __init__(self, repo: FirestoreRepo):
        self.repo = repo
        # PermissionGuard: 실제로는 별도 모듈로 분리해야 하나 운영 최소로 내부에 단순 구현
        # 추후 services.permission_guard import
        
    def _apply_permissions(self, nodes: List[Dict], edges: List[Dict]) -> Tuple[List[Dict], List[Dict]]:
        """
        보안 및 상태 필터링
        - Active=False 제외
        - Review Status != Approved 제외
        - Security Level 검사 (여기선 L1만 허용하거나, 사용자 권한 비교)
        - 운영 최소: Active=True만 남기고 Review Status는 API 요청 단계에서 이미 필터링되었다고 가정
          (FirestoreRepo가 기본적으로 Active=True만 가져옴)
        """
        # Node Filter
        valid_node_ids = set()
        filtered_nodes = []
        
        for n in nodes:
            # 문서 노드인 경우 추가 검증? (이미 서빙 인덱스 빌드 시 걸러졌다고 가정)
            filtered_nodes.append(n)
            valid_node_ids.add(n["id"])
            
        # Edge Filter
        filtered_edges = []
        for e in edges:
            if e["source"] in valid_node_ids and e["target"] in valid_node_ids:
                filtered_edges.append(e)
                
        return filtered_nodes, filtered_edges

    def get_overview(self, limit: int = None, mode: str = "hybrid", include_docs: bool = True) -> Dict[str, Any]:
        """
        초기 그래프 로드 (Full Graph View)
        - mode="hybrid": Concepts + Top Docs (Default)
        - mode="overview": Concept-Only View + Semantic Edges (Legacy)
        """
        limit = limit or GRAPH_INIT_MAX_NODES
        # Repo fetches concepts (sorted by doc_count)
        data = self.repo.get_graph_init(limit_nodes=limit)
        
        nodes = []
        edges = []
        node_ids = set()
        
        # 1. Add Concepts
        for c in data.get("concepts", []):
            cid = c.get("concept_id")
            if not cid or cid in node_ids: continue
            
            meta = c.get("meta", {})
            nodes.append({
                "id": cid,
                "label": meta.get("name", cid),
                "group": "concept",
                "type": meta.get("type", "OTHERS"),
                "size": c.get("doc_count", 1) * 2 # Slight boost
            })
            node_ids.add(cid)
            
            # 2. Add Concept-Concept Edges (Semantic Connectivity)
            # Always add in hybrid mode too for context
            neighbors = c.get("neighbors", []) # Co-occurrence
            for n in neighbors:
                nid = n.get("concept_id")
                if nid and nid in node_ids: # Only draw if target exists in current view
                        edges.append({
                            "source": cid,
                            "target": nid,
                            "value": n.get("weight", 0.5), # Co-occurrence strength
                            "edge_label": "related",
                            "type": "cooc"
                        })

        # 3. Add Documents (Default behavior now)
        if mode == "hybrid" or include_docs:
            for c in data.get("concepts", []):
                cid = c.get("concept_id")
                if cid not in node_ids: continue
                
                # Fetch Top Docs for this concept
                top_docs = c.get("top_docs", [])[:5] # Strict limit per concept to avoid explosion
                for td in top_docs:
                    doc_id = td.get("doc_id")
                    if not doc_id: continue
                    
                    if doc_id not in node_ids:
                        nodes.append({
                            "id": doc_id,
                            "label": td.get("title", doc_id), # Title pre-injected
                            "group": "document",
                            "type": "pdf",
                            "size": 1
                        })
                        node_ids.add(doc_id)
                    
                    edges.append({
                        "source": doc_id, # Doc mentions Concept
                        "target": cid,
                        "rank_score": td.get("score", 0.5),
                        "edge_label": "mentions",
                        "type": "mentions"
                    })

        # 4. Title Correction (Legacy Fallback)
        # If title missing in top_docs, try doc list from repo
        doc_title_map = {d.get("doc_id"): d.get("title") for d in data.get("docs", [])}
        for n in nodes:
            if n.get("group") == "document" and n["id"] in doc_title_map:
                if n["label"] == n["id"]: # Only update if label is ID
                    n["label"] = doc_title_map[n["id"]]

        # Filter
        clean_nodes, clean_edges = self._apply_permissions(nodes, edges)
        
        return {
            "nodes": clean_nodes,
            "links": clean_edges,
            "stats": {"node_count": len(clean_nodes), "link_count": len(clean_edges)}
        }

    def expand_neighborhood(self, node_id: str, node_type: str, doc_limit: int = 15) -> Dict[str, Any]:
        """특정 노드 클릭 시 주변 확장 (Strict Limit)"""
        nodes = []
        edges = []
        node_ids = set() # To prevent duplicates in response
        
        # Center Node
        nodes.append({
            "id": node_id, 
            "group": node_type,
            "label": node_id # Placeholder, frontend usually has label
        })
        node_ids.add(node_id)
        
        neighbors_data = None
        if node_type == "document":
            neighbors_data = self.repo.get_doc_neighbors(node_id)
            if neighbors_data:
                # Doc -> Concepts (Limit 20)
                concepts = neighbors_data.get("top_concepts", [])[:20]
                for c in concepts:
                    cid = c.get("concept_id")
                    if not cid or cid in node_ids: continue
                    nodes.append({
                        "id": cid, 
                        "group": "concept",
                        "type": c.get("concept_type", "OTHERS"), # ranker saved this
                        "label": c.get("concept_name", cid),
                        "size": c.get("mentions", 1)
                    })
                    node_ids.add(cid)
                    edges.append({
                        "source": node_id,
                        "target": cid,
                        "rank_score": c.get("score", 0.5),
                        "edge_label": "mentions",
                        "type": "mentions"
                    })
                    
        elif node_type == "concept":
            neighbors_data = self.repo.get_concept_neighbors(node_id)
            if neighbors_data:
                # 1. Concept -> Docs (Limit 15)
                # To support 2-hop (Concept -> Doc -> Concept), we need full doc details
                top_docs_meta = neighbors_data.get("top_docs", [])[:doc_limit]
                doc_ids = [d.get("doc_id") for d in top_docs_meta if d.get("doc_id")]
                
                # Batch Fetch Docs from Serving Layer
                # Create refs for graph_serving_docs
                refs = [self.repo.db.collection("graph_serving_docs").document(did) for did in doc_ids]
                docs_snapshot = self.repo.db.get_all(refs)
                
                # Batch Fetch 3rd Hop (Concept Layers)
                # Note: docs_snapshot is generator, consume once.
                
                level2_concept_ids = set()
                
                for doc in docs_snapshot:
                    if not doc.exists: continue
                    d_data = doc.to_dict()
                    did = doc.id
                    
                    if did not in node_ids:
                        nodes.append({
                            "id": did,
                            "group": "document",
                            "type": "pdf",
                            "label": d_data.get("title", did)
                        })
                        node_ids.add(did)
                    
                    # Edge: Concept -> Doc (Reverse of mentions)
                    edges.append({
                        "source": did,
                        "target": node_id,
                        "rank_score": 0.8, # Strong link
                        "edge_label": "mentions",
                        "type": "mentions"
                    })
                    
                    # 2-Hop: Doc -> Top Concepts
                    # Add Top 5 Concepts of this doc
                    sub_concepts = d_data.get("top_concepts", [])[:5]
                    for sub_c in sub_concepts:
                        scid = sub_c.get("concept_id")
                        if not scid: continue
                        
                        if scid not in node_ids:
                            nodes.append({
                                "id": scid,
                                "group": "concept",
                                "type": sub_c.get("concept_type", "OTHERS"),
                                "label": sub_c.get("concept_name", scid),
                                "size": sub_c.get("mentions", 1)
                            })
                            node_ids.add(scid)
                            
                        # Edge: Doc -> Concept
                        if scid != node_id: 
                             edges.append({
                                "source": did,
                                "target": scid,
                                "rank_score": sub_c.get("score", 0.5),
                                "edge_label": "mentions",
                                "type": "mentions"
                            })
                                    # Collect L2 ID for 3rd Hop (Only if not same as center)
                        if scid != node_id:
                            level2_concept_ids.add(scid)
                
                # Now fetch L3 based on collected IDs
                if level2_concept_ids:
                    # Limit to avoid explosion - Increased as per user request (Unlimited-ish)
                    l2_chunks = list(level2_concept_ids) # Iterate all
                    
                    chunk_size = 10
                    l2_id_chunks = [l2_chunks[i:i + chunk_size] for i in range(0, len(l2_chunks), chunk_size)]
                    
                    for chunk in l2_id_chunks:
                        l2_refs = [self.repo.db.collection("graph_serving_concepts").document(cid) for cid in chunk]
                        try:
                            l2_docs = self.repo.db.get_all(l2_refs)
                            
                            for cd in l2_docs:
                                if not cd.exists: continue
                                c_data = cd.to_dict()
                                cid = cd.id
                                
                                # Get Top Docs for this Level 2 Concept (3rd Hop)
                                l3_docs = c_data.get("top_docs", []) 
                                for l3d in l3_docs:
                                    l3_did = l3d.get("doc_id")
                                    if not l3_did: continue
                                    
                                    if l3_did not in node_ids:
                                        nodes.append({
                                            "id": l3_did,
                                            "group": "document",
                                            "type": "pdf",
                                            "label": l3d.get("title", l3_did),
                                            "size": 0.8
                                        })
                                        node_ids.add(l3_did)
                                        
                                    edges.append({
                                        "source": l3_did,
                                        "target": cid,
                                        "rank_score": l3d.get("score", 0.5),
                                        "edge_label": "mentions",
                                        "type": "mentions"
                                    })
                        except Exception as e:
                            logger.warning(f"Error expanding 3rd hop chunk: {e}")

                # 2. Concept -> Concept (Neighbors) - Show semantics (Limit 10)
                neighbors = neighbors_data.get("neighbors", [])[:10]
                for n in neighbors:
                    nid = n.get("concept_id")
                    if not nid: continue
                    # We assume neighbor node exists or will be fetched?
                    # For performance, maybe just add node with ID.
                    if nid not in node_ids:
                        nodes.append({
                            "id": nid,
                            "group": "concept",
                            "label": nid, # Fallback
                            "type": "neighbor"
                        })
                        node_ids.add(nid)

                    edges.append({
                        "source": node_id,
                        "target": nid,
                        "value": n.get("weight", 0.5),
                        "edge_label": "related",
                        "type": "cooc"
                    })
        
        # Permission Filter
        clean_nodes, clean_edges = self._apply_permissions(nodes, edges)
        
        return {
            "nodes": clean_nodes,
            "links": clean_edges
        }
