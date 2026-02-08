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
    limit: Optional[int] = Query(None, description="Max nodes count"),
    mode: Optional[str] = Query("overview", description="Mode: 'overview' (Concept-Only) or 'hybrid'"),
    include_docs: Optional[bool] = Query(False, description="Include Example Docs in Overview?")
):
    try:
        if limit is not None and (limit < 1 or limit > 500):
             raise HTTPException(status_code=400, detail="Limit must be between 1 and 500")

        service = get_service(request)
        result = service.get_overview(limit=limit, mode=mode, include_docs=include_docs)
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

@router.get("/neighborhood")
async def get_neighborhood(
    request: Request,
    node_id: str,
    node_type: str = Query(..., description="document or concept"),
    limit: Optional[int] = Query(30)
):
    # Expand와 로직 동일 (프론트에서 용어 혼용 시 대비 alias)
    return await expand_graph(request, node_id, node_type, limit)
