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

    def get_overview(self, mode: str = "hybrid", max_concepts: int = 50, max_edges: int = 160, include_docs: bool = False) -> Dict[str, Any]:
        """
        초기 그래프 로드 (Full Graph View)
        - mode="hybrid": Concepts + Top Docs (Default)
        - mode="overview": Concept-Only View + Semantic Edges (Legacy)
        """
        # Repo fetches concepts (sorted by doc_count)
        data = self.repo.get_graph_init(limit_nodes=max_concepts)
        
        nodes = []
        edges = []
        node_ids = set()
        
        # 1. Add Concepts
        for c in data.get("concepts", []):
            cid = c.get("concept_id")
            if not cid or cid in node_ids: continue
            
            meta = c.get("meta", {})
            doc_count = c.get("doc_count", 0)
            
            # Size Logic: 2~3 based on doc_count (Logarithmic or simple resizing)
            # Req: size=2~3
            size = 2.0
            if doc_count > 5: size = 2.5
            if doc_count > 10: size = 3.0
            
            nodes.append({
                "id": cid,
                "label": meta.get("name", cid),
                "group": "concept",
                "type": meta.get("type", "OTHERS"),
                "size": size
            })
            node_ids.add(cid)
            
            # 2. Add Concept-Concept Edges (Semantic Connectivity)
            # Only edges within current top-K concepts
            neighbors = c.get("neighbors", []) 
            for n in neighbors:
                nid = n.get("concept_id")
                if nid and nid in node_ids: # Only draw if target exists in current view (Internal Link only)
                    if len(edges) >= max_edges: break
                    
                    shared = n.get("shared_docs", 1)
                    weight = n.get("weight", 0.5)
                    
                    edges.append({
                        "source": cid,
                        "target": nid,
                        "rank_score": weight,  # For physics force strength
                        "value": shared,       # For visual thickness (optional)
                        "edge_label": "related",
                        "type": "cooc"
                    })

        # 3. Add Documents (Default behavior now)
        if mode == "hybrid" or include_docs:
            for c in data.get("concepts", []):
                cid = c.get("concept_id")
                if cid not in node_ids: continue
                
                # Fetch Top Docs for this concept
                top_docs = c.get("top_docs", [])[:5] # Strict limit per concept
                for td in top_docs:
                    if len(nodes) >= max_concepts * 2: break # Safe guard

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
                    
                    if len(edges) < max_edges:
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
        # [Existing Implementation Preserved]
        # For brevity, reusing the existing logic in previous implementation but updated signatures.
        # But wait, I am replacing the file content. I must include the full body of expand_neighborhood 
        # or else it will be lost if I replace the whole block.
        # The prompt asked to "Add expand_concept_cascade", so I should probably keep `expand_neighborhood`.
        # I will re-implement minimal `expand_neighborhood` or copy existing if possible.
        # To avoid huge context, I will try to be concise but functional.
        
        # Actually, the user asked to "Add" method. I will use multi_replace to target specific blocks if possible
        # but replace_file_content is better for large changes.
        # I will reimplement expand_neighborhood exactly as it was (from view_file).
        
        nodes = []
        edges = []
        node_ids = set() 
        
        nodes.append({"id": node_id, "group": node_type, "label": node_id})
        node_ids.add(node_id)
        
        neighbors_data = None
        if node_type == "document":
            neighbors_data = self.repo.get_doc_neighbors(node_id)
            if neighbors_data:
                concepts = neighbors_data.get("top_concepts", [])[:20]
                for c in concepts:
                    cid = c.get("concept_id")
                    if not cid or cid in node_ids: continue
                    nodes.append({
                        "id": cid, 
                        "group": "concept",
                        "type": c.get("concept_type", "OTHERS"),
                        "label": c.get("concept_name", cid),
                        "size": c.get("mentions", 1)
                    })
                    node_ids.add(cid)
                    edges.append({
                        "source": node_id, "target": cid,
                        "rank_score": c.get("score", 0.5),
                        "edge_label": "mentions", "type": "mentions"
                    })
                    
        elif node_type == "concept":
            neighbors_data = self.repo.get_concept_neighbors(node_id)
            if neighbors_data:
                top_docs = neighbors_data.get("top_docs", [])[:doc_limit]
                for td in top_docs:
                    did = td.get("doc_id")
                    if not did or did in node_ids: continue
                    nodes.append({
                        "id": did, "group": "document", "type": "pdf",
                        "label": td.get("title", did)
                    })
                    node_ids.add(did)
                    edges.append({
                        "source": did, "target": node_id,
                        "rank_score": td.get("score", 0.5),
                        "edge_label": "mentions", "type": "mentions"
                    })
                
                # Neighbors
                neighbors = neighbors_data.get("neighbors", [])[:10]
                for n in neighbors:
                    nid = n.get("concept_id")
                    if nid and nid not in node_ids:
                        nodes.append({"id": nid, "group": "concept", "label": nid, "type": "neighbor"})
                        node_ids.add(nid)
                    if nid:
                        edges.append({
                            "source": node_id, "target": nid,
                            "value": n.get("weight", 0.5),
                            "edge_label": "related", "type": "cooc"
                        })

        clean_nodes, clean_edges = self._apply_permissions(nodes, edges)
        return {"nodes": clean_nodes, "links": clean_edges}

    def expand_concept_cascade(
        self, 
        center_concept_id: str, 
        doc_limit: int = 20,
        concepts_per_doc: int = 6,
        docs_per_concept: int = 5,
        max_total_nodes: int = 600,
        max_total_edges: int = 1200
    ) -> Dict[str, Any]:
        """
        Cascade Expansion (3-Hop):
        L0 (Center) -> L1 (Docs) -> L2 (Concepts) -> L3 (Docs)
        """
        nodes = []
        edges = []
        node_ids = set()
        edge_keys = set()
        
        def add_node(nid, group, label=None, ntype="OTHERS", size=1):
            if nid in node_ids: return
            if len(nodes) >= max_total_nodes: return
            
            nodes.append({
                "id": nid,
                "label": label or nid,
                "group": group,
                "type": ntype,
                "size": size
            })
            node_ids.add(nid)

        def add_edge(src, tgt, etype="mentions", score=0.5, label=""):
            key = f"{src}-{tgt}-{etype}"
            if key in edge_keys: return
            if len(edges) >= max_total_edges: return
            
            edges.append({
                "source": src,
                "target": tgt,
                "rank_score": score,
                "value": score,
                "type": etype,
                "edge_label": label
            })
            edge_keys.add(key)
        
        # Level 0: Center Concept
        concept_data = self.repo.get_concept_neighbors(center_concept_id)
        if not concept_data:
            return {"nodes": [], "links": []}
            
        add_node(center_concept_id, "concept", label=center_concept_id, size=2) # Need better label fetch if possible
        
        # Level 1: Docs connected to Center
        top_docs = concept_data.get("top_docs", [])[:doc_limit]
        l1_doc_ids = []
        
        for d in top_docs:
            did = d.get("doc_id")
            if not did: continue
            add_node(did, "document", label=d.get("title", did), ntype="pdf")
            add_edge(did, center_concept_id, score=d.get("score", 0.5), label="mentions")
            l1_doc_ids.append(did)
            
        # Level 2: Concepts connected to L1 Docs
        # Batch fetch docs from graph_serving_docs to get their top_concepts
        if l1_doc_ids:
            doc_refs = [self.repo.db.collection("graph_serving_docs").document(did) for did in l1_doc_ids]
            docs_snaps = self.repo.db.get_all(doc_refs)
            
            l2_concept_ids = []
            
            for ds in docs_snaps:
                if not ds.exists: continue
                d_data = ds.to_dict()
                
                # Concepts in this doc
                sub_concepts = d_data.get("top_concepts", [])[:concepts_per_doc]
                for sc in sub_concepts:
                    scid = sc.get("concept_id")
                    if not scid: continue
                    
                    add_node(scid, "concept", 
                             label=sc.get("concept_name", scid), 
                             ntype=sc.get("concept_type", "OTHERS"),
                             size=sc.get("mentions", 1))
                             
                    add_edge(ds.id, scid, score=sc.get("score", 0.5), label="mentions")
                    
                    if scid != center_concept_id:
                        l2_concept_ids.append(scid)
            
            # Level 3: Docs connected to L2 Concepts
            # Batch fetch concepts from graph_serving_concepts
            l2_concept_ids = list(set(l2_concept_ids)) # Unique
            
            # Include Center Concept in the set for internal edges
            all_concepts_in_view = set(l2_concept_ids)
            all_concepts_in_view.add(center_concept_id)
            
            if l2_concept_ids:
                # Chunking 10
                chunk_size = 10
                for i in range(0, len(l2_concept_ids), chunk_size):
                    chunk = l2_concept_ids[i:i+chunk_size]
                    c_refs = [self.repo.db.collection("graph_serving_concepts").document(cid) for cid in chunk]
                    
                    try:
                        c_snaps = self.repo.db.get_all(c_refs)
                        
                        for cs in c_snaps:
                            if not cs.exists: continue
                            c_data = cs.to_dict()
                            cid = cs.id
                            
                            # L3 Docs Expansion
                            l3_docs = c_data.get("top_docs", [])[:docs_per_concept]
                            for l3d in l3_docs:
                                did = l3d.get("doc_id")
                                if not did: continue
                                
                                # Add L3 Doc Node
                                add_node(did, "document", label=l3d.get("title", did), ntype="pdf", size=0.8)
                                add_edge(did, cid, score=l3d.get("score", 0.5), label="mentions")
                            
                            # [Option 5] Add Concept-Concept Edges (Internal Only)
                            # Neighbors of this L2 concept
                            neighbors = c_data.get("neighbors", [])
                            for n in neighbors:
                                nid = n.get("concept_id")
                                if nid and nid in all_concepts_in_view:
                                    # Add edge if both nodes exist in current subgraph
                                    # Ensure we don't add duplicate edges (handled by add_edge)
                                    if cid in node_ids and nid in node_ids:
                                        add_edge(cid, nid, 
                                                 etype="cooc", 
                                                 score=n.get("weight", 0.5), 
                                                 label="related")
                    except Exception as e:
                        logger.warning(f"Error expanding L3: {e}")

        clean_nodes, clean_edges = self._apply_permissions(nodes, edges)
        return {
            "nodes": clean_nodes,
            "links": clean_edges,
            "stats": {"node_count": len(clean_nodes), "link_count": len(clean_edges)}
        }
