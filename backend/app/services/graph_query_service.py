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

    def get_overview(self, limit: int = None) -> Dict[str, Any]:
        """초기 그래프 로드 (Concept-First Approach for Verified Edges)"""
        limit = limit or GRAPH_INIT_MAX_NODES
        data = self.repo.get_graph_init(limit_nodes=limit)
        
        nodes = []
        edges = []
        node_ids = set()
        
        # 1. Concepts를 중심으로 순회 (Top Concepts)
        for c in data.get("concepts", []):
            cid = c.get("concept_id")
            if cid in node_ids: continue
            
            # Concept Node 추가
            meta = c.get("meta", {})
            nodes.append({
                "id": cid,
                "label": meta.get("name", cid),
                "type": "concept",
                "concept_type": meta.get("type", "OTHERS"),
                "size": c.get("doc_count", 1)
            })
            node_ids.add(cid)
            
            # 2. 해당 Concept에 연결된 Top Docs를 순회하여 Edge 생성
            top_docs = c.get("top_docs", [])
            for td in top_docs:
                doc_id = td.get("doc_id")
                
                # Document Node 추가 (아직 없으면)
                if doc_id not in node_ids:
                    # [Note] top_docs 안에는 title 정보가 없을 수 있음 (Serving Index 빌드 시점에 따라)
                    # 하지만 연결성을 위해 일단 노드는 생성해야 함.
                    # Build 시점에 doc_meta가 추가되었다면 좋겠지만, 없으면 doc_id 사용.
                    # repo.get_graph_init의 'docs' 리스트를 참조하면 Title을 알 수도 있음.
                    nodes.append({
                        "id": doc_id,
                        "label": doc_id, # 임시로 ID 사용 (아래에서 보정)
                        "type": "document",
                        "size": 1
                    })
                    node_ids.add(doc_id)
                
                # Edge 추가 (Concept <-> Doc)
                edges.append({
                    "source": doc_id,  # Doc -> Concept
                    "target": cid,
                    "score": td.get("score", 0),
                    "type": "mentions"
                })

        # 3. Title 보정 (data['docs']에 있는 정보 활용)
        # Concept의 top_docs에는 title이 없을 수 있으므로, 별도로 가져온 docs 리스트에서 title을 찾아 매핑
        doc_title_map = {}
        for d in data.get("docs", []):
            doc_title_map[d.get("doc_id")] = d.get("title", d.get("doc_id"))
            
        for n in nodes:
            if n["type"] == "document" and n["id"] in doc_title_map:
                n["label"] = doc_title_map[n["id"]]

        # Permission Filter
        clean_nodes, clean_edges = self._apply_permissions(nodes, edges)
        
        return {
            "nodes": clean_nodes,
            "links": clean_edges, # [Fix] Frontend expects 'links', not 'edges'
            "stats": {"node_count": len(clean_nodes), "link_count": len(clean_edges)}
        }

    def expand_neighborhood(self, node_id: str, node_type: str, limit: int = 50) -> Dict[str, Any]:
        """특정 노드 클릭 시 주변 확장"""
        nodes = []
        edges = []
        
        # Add Center Node (Client가 이미 알고 있겠지만 안전하게 포함)
        nodes.append({"id": node_id, "type": node_type, "label": node_id}) # 정보 부족 시 ID로
        
        neighbors_data = None
        if node_type == "document":
            neighbors_data = self.repo.get_doc_neighbors(node_id)
            if neighbors_data:
                # Doc -> Concepts
                concepts = neighbors_data.get("top_concepts", [])[:limit]
                for c in concepts:
                    cid = c.get("concept_id")
                    nodes.append({
                        "id": cid, 
                        "type": "concept", 
                        "label": c.get("name", cid),
                        "concept_type": c.get("type", "OTHERS")
                    })
                    edges.append({
                        "source": node_id,
                        "target": cid,
                        "score": c.get("score", 0),
                        "type": "mentions"
                    })
                    
        elif node_type == "concept":
            neighbors_data = self.repo.get_concept_neighbors(node_id)
            if neighbors_data:
                # Concept -> Docs
                docs = neighbors_data.get("top_docs", [])[:limit]
                for d in docs: # d: {doc_id, score, ...}
                    did = d.get("doc_id")
                    nodes.append({
                        "id": did,
                        "type": "document",
                        "label": did # 제목 조회하려면 추가 쿼리 필요
                    })
                    edges.append({
                        "source": did,  # Mentions direction: Doc -> Concept
                        "target": node_id,
                        "score": d.get("score", 0),
                        "type": "mentions"
                    })
        
        # Permission Filter
        clean_nodes, clean_edges = self._apply_permissions(nodes, edges)
        
        return {
            "nodes": clean_nodes,
            "links": clean_edges
        }
