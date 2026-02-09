import logging
import os
from typing import Optional, List
from fastapi import APIRouter, Request, HTTPException, Query, BackgroundTasks
from app.services.firestore_repo import FirestoreRepo
from app.core.gcp_clients import get_firestore_client

logger = logging.getLogger("TreeAPI")
router = APIRouter(prefix="/api/tree", tags=["Tree"])

# [Legacy Support] 백엔드 호환성을 위해 구버전 경로도 지원
legacy_router = APIRouter(tags=["Tree-Legacy"])

DEFAULT_LIMIT = int(os.getenv("TREE_PAGE_SIZE_DEFAULT", 100))
MAX_LIMIT = int(os.getenv("TREE_PAGE_SIZE_MAX", 300))

import hashlib
from typing import Dict, Any

@router.post("/refresh")
async def refresh_tree_index(
    request: Request,
    background_tasks: BackgroundTasks
):
    """
    Force refresh tree index for current scope (Async)
    """
    auth_ctx = getattr(request.state, "auth_ctx", None)
    if not auth_ctx:
        raise HTTPException(status_code=401, detail="Unauthorized")
        
    from app.services.tree_indexer_service import TreeIndexerService
    
    # Run in background
    background_tasks.add_task(
        TreeIndexerService().refresh_all, 
        auth_ctx.tenant_id, 
        auth_ctx.engagement_id
    )
    
    return {"message": "Tree indexing started."}

@router.get("/full")
async def get_full_tree(request: Request):
    """
    [Migration] Legacy UI Support: Return full recursive tree structure from tree_index.
    Replaces /files/virtual-tree but uses efficient 'tree_index' collection.
    """
    auth_ctx = getattr(request.state, "auth_ctx", None)
    if not auth_ctx:
        raise HTTPException(status_code=401, detail="Unauthorized")
        
    try:
        db = get_firestore_client()
        tenant_id = auth_ctx.tenant_id
        engagement_id = auth_ctx.engagement_id
        
        # 1. Fetch all tree nodes
        docs_stream = db.collection("tree_index")\
            .where("tenant_id", "==", tenant_id)\
            .where("engagement_id", "==", engagement_id)\
            .stream()
            
        nodes = [d.to_dict() for d in docs_stream]
        
        # 2. Auto-Indexing if empty (Cold Start)
        if not nodes:
            from app.services.tree_indexer_service import TreeIndexerService
            indexer = TreeIndexerService()
            indexer.refresh_all(tenant_id, engagement_id)
            
            # Re-fetch
            docs_stream = db.collection("tree_index")\
                .where("tenant_id", "==", tenant_id)\
                .where("engagement_id", "==", engagement_id)\
                .stream()
            nodes = [d.to_dict() for d in docs_stream]
            
        # 3. Build Hierarchy (Flat -> Tree)
        folder_map = {}
        
        # Create Nodes
        for n in nodes:
            path = n.get("folder_path")
            if not path: continue
            
            name = "Root"
            if path != "/":
                name = path.strip("/").split("/")[-1]
            
            folder_map[path] = {
                "name": name,
                "id": path, 
                "children": [], 
                "is_folder": True
            }

        # Link Children
        for n in nodes:
            current_path = n.get("folder_path")
            if current_path not in folder_map: continue
            
            parent_node = folder_map[current_path]
            
            # Documents
            for doc in n.get("children_docs", []):
                parent_node["children"].append({
                    "name": doc.get("title", "Untitled"),
                    "id": doc.get("doc_id"),
                    "mime_type": "application/pdf", 
                    "is_folder": False
                })
                
            # Folders
            for sub in n.get("children_folders", []):
                sub_path = sub.get("path")
                if sub_path in folder_map:
                    child_node = folder_map[sub_path]
                    if child_node not in parent_node["children"]:
                        parent_node["children"].append(child_node)
                else:
                    # Self-healing if index incomplete
                    new_node = {
                        "name": sub.get("name"), 
                        "id": sub_path, 
                        "children": [], 
                        "is_folder": True
                    }
                    folder_map[sub_path] = new_node
                    parent_node["children"].append(new_node)
        
        return folder_map.get("/", {"name": "Root", "children": [], "is_folder": True})
        
    except Exception as e:
         raise HTTPException(status_code=500, detail=f"Tree Build Error: {str(e)}")

# [Legacy Support] 프론트엔드 호환성을 위한 구버전 경로
@legacy_router.get("/files/virtual-tree")
async def get_virtual_tree_legacy(request: Request):
    """프론트엔드가 /files/virtual-tree를 호출하면 /api/tree/full과 동일한 결과 반환"""
    return await get_full_tree(request)

@router.get("")
async def get_tree_items(
    request: Request,
    folder: str = Query("/", description="Folder path to browse")
):
    """
    Lazy Loaded Tree: tree_index 컬렉션을 조회하여 폴더 및 파일 목록 반환
    """
    auth_ctx = getattr(request.state, "auth_ctx", None)
    if not auth_ctx:
        raise HTTPException(status_code=401, detail="Unauthorized")
        
    repo = FirestoreRepo(auth_ctx)
    
    # 1. Path Normalization (Must match build_tree_index.py)
    normalized_path = folder.strip()
    if not normalized_path.startswith("/"):
        normalized_path = "/" + normalized_path
    if not normalized_path.endswith("/"):
        normalized_path = normalized_path + "/"
        
    try:
        # 2. Key Generation
        path_hash = hashlib.sha256(normalized_path.encode('utf-8')).hexdigest()[:16]
        tree_key = f"{auth_ctx.tenant_id}__{auth_ctx.engagement_id}__{path_hash}"
        
        # 3. Fetch from tree_index
        # Using repo.db directly for this optimized query
        doc_ref = repo.get_firestore_client().collection("tree_index").document(tree_key).get()
        
        if not doc_ref.exists:
            # If root path not found, try auto-indexing (Cold Start)
            if normalized_path == "/":
                logger.info(f"Root tree index missing for {tree_key}. Triggering auto-index.")
                from app.services.tree_indexer_service import TreeIndexerService
                
                # Sync execution clearly for first load (might take time)
                # For better UX, maybe async? But user wants to see tree.
                # Let's do sync for root.
                TreeIndexerService().refresh_all(auth_ctx.tenant_id, auth_ctx.engagement_id)
                
                # Retry fetch
                doc_ref = repo.get_firestore_client().collection("tree_index").document(tree_key).get()
                if not doc_ref.exists:
                     return {"current_path": "/", "folders": [], "files": []}
            else:
                return {
                    "current_path": normalized_path,
                    "folders": [],
                    "files": []
                }
            
        from app.services.permission_service import PermissionGuard
        
        data = doc_ref.to_dict()
        
        # 4. Filter by permissions (Enforce Security)
        raw_files = data.get("children_docs", [])
        
        # Inject Context scope for PermissionGuard (since it checks tenant/engagement equality)
        # Tree Index has them at root
        current_tenant = data.get("tenant_id")
        current_engagement = data.get("engagement_id")
        
        # Prepare for filtering
        # We need to inject these into each file dict because PermissionGuard checks doc['tenant_id']
        candidates = []
        for f in raw_files:
            # Shallow copy to avoid mutation if cached? (Firestore to_dict is fresh)
            f_enrich = f.copy()
            f_enrich["tenant_id"] = current_tenant
            f_enrich["engagement_id"] = current_engagement
            # [Fix] Frontend expects 'name', but DB stores 'title'. Map it here.
            f_enrich["name"] = f.get("title", f.get("name", "Untitled"))
            
            if len(candidates) == 0:
                logger.info(f"[DEBUG-TREE] First Enrichment: {f_enrich}") # Debug log
            
            candidates.append(f_enrich)
            
        filtered_files = PermissionGuard.filter_docs(auth_ctx, candidates)
        
        return {
            "current_path": data.get("folder_path"),
            "folders": data.get("children_folders", []),
            "files": filtered_files
        }
        
    except Exception as e:
        logger.error(f"Tree Index Query Failed: {e}")
        raise HTTPException(status_code=500, detail="Failed to load tree structure")
