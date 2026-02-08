import logging
from fastapi import APIRouter, Request, Query, HTTPException, Depends
from typing import Optional
from app.services.firestore_repo import FirestoreRepo
from app.services.graph_query_service import GraphQueryService

router = APIRouter(prefix="/api/graph", tags=["Graph"])
logger = logging.getLogger("GraphAPI")

def get_service(request: Request) -> GraphQueryService:
    # Dependency Injection
    auth_ctx = getattr(request.state, "auth_ctx", None)
    if not auth_ctx:
        logger.error("Auth context missing in request state")
        raise HTTPException(status_code=401, detail="Unauthorized")
    
    repo = FirestoreRepo(auth_ctx)
    return GraphQueryService(repo)

@router.get("/init")
async def get_graph_init(
    request: Request,
    mode: Optional[str] = Query("overview", description="Mode: 'overview' (Concept-Only) or 'hybrid'"),
    max_concepts: Optional[int] = Query(50, description="Max concept nodes"),
    max_edges: Optional[int] = Query(160, description="Max edges"),
    include_docs: Optional[bool] = Query(False, description="Include Example Docs in Overview?")
):
    try:
        if max_concepts < 1 or max_concepts > 500:
             raise HTTPException(status_code=400, detail="max_concepts must be between 1 and 500")

        service = get_service(request)
        result = service.get_overview(
            mode=mode, 
            max_concepts=max_concepts, 
            max_edges=max_edges, 
            include_docs=include_docs
        )
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Graph Init Failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/expand")
async def expand_graph(
    request: Request,
    node_id: str,
    node_type: str = Query(..., description="document or concept"),
    doc_limit: Optional[int] = Query(15, description="Max docs to show"),
    limit: Optional[int] = Query(30, description="Legacy limit param (unused now)")
):
    try:
        if not node_id or not node_id.strip():
            raise HTTPException(status_code=400, detail="Node ID is required")
            
        if node_type not in ("document", "concept"):
            raise HTTPException(status_code=400, detail="Invalid node_type. Must be 'document' or 'concept'")
            
        service = get_service(request)
        result = service.expand_neighborhood(node_id=node_id, node_type=node_type, doc_limit=doc_limit)
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Graph Expand Failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/subgraph")
async def get_subgraph(
    request: Request,
    center_concept_id: str = Query(..., description="Center Concept ID"),
    mode: str = Query("cascade", description="Expansion Mode"),
    doc_limit: int = Query(20, description="L1 Docs Limit"),
    concepts_per_doc: int = Query(6, description="L2 Concepts per Doc"),
    docs_per_concept: int = Query(5, description="L3 Docs per Concept"),
    max_total_nodes: int = Query(600, description="Safety Cap Nodes"),
    max_total_edges: int = Query(1200, description="Safety Cap Edges")
):
    try:
        if not center_concept_id:
            raise HTTPException(status_code=400, detail="center_concept_id is required")
            
        service = get_service(request)
        
        if mode == "cascade":
            result = service.expand_concept_cascade(
                center_concept_id=center_concept_id,
                doc_limit=doc_limit,
                concepts_per_doc=concepts_per_doc,
                docs_per_concept=docs_per_concept,
                max_total_nodes=max_total_nodes,
                max_total_edges=max_total_edges
            )
            return result
        else:
             raise HTTPException(status_code=400, detail=f"Unknown mode: {mode}")

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Graph Subgraph Failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/neighborhood")
async def get_neighborhood(
    request: Request,
    node_id: str,
    node_type: str = Query(..., description="document or concept"),
    limit: Optional[int] = Query(30)
):
    # Expand와 로직 동일 (프론트에서 용어 혼용 시 대비 alias)
    return await expand_graph(request, node_id, node_type, limit)
