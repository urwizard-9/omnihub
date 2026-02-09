from fastapi import APIRouter, HTTPException, BackgroundTasks, Request, Query, Depends
# from app.core.gcp_clients import db, get_drive_service # [Remapped]
from app.core.gcp_clients import get_firestore_client, get_drive_service
from app.services.log_service import log_user_action
from app.models.log import ActionType
# from app.dependencies import get_current_user # [Fixed] Path mismatch
from app.core.dependencies import get_current_user
from app.models.user import UserSchema
from typing import Optional

#파일과 관련된 모든 요청을 처리하는 곳

router = APIRouter()



def get_db():
    return get_firestore_client()

# 1. Real Drive Proxy API
@router.get("/files/drive/proxy")
async def get_drive_files_proxy(
    folder_id: str = Query("root"),
    q: Optional[str] = Query(None),
    current_user: UserSchema = Depends(get_current_user)
):
    """
    실제 구글 드라이브의 파일 목록을 실시간으로 중계합니다. (탐색기용)
    q 파라미터가 있으면 '검색' 모드로 동작하고, 없으면 '폴더 조회' 모드로 동작합니다.
    """
    from app.utils.error_handler import raise_classified_http_exception
    
    try:
        # [Security Fix] Use User Credentials instead of Service Account
        from app.services.drive_service import get_user_drive_service
        service = get_user_drive_service(current_user)
        
        # Query Construction
        if q:
            # Search Mode: Name contains 'q'
            # Note: Google Drive API 'contains' is case-insensitive for 'name'
            query = f"name contains '{q}' and trashed = false"
        else:
            # Browse Mode: List children of folder
            # "root" alias works for User Drive as well ("My Drive")
            query = f"'{folder_id}' in parents and trashed = false"
        
        # 필요한 필드만 콕 집어서 가져옴 (속도 최적화)
        fields = "files(id, name, mimeType, iconLink, webViewLink, hasThumbnail, thumbnailLink, parents)"
        
        results = service.files().list(
            q=query,
            pageSize=100,
            fields=fields,
            orderBy="folder, name",
            supportsAllDrives=True,
            includeItemsFromAllDrives=True
        ).execute()
        
        return {"files": results.get('files', [])}
        
    except Exception as e:
        # [Log Plan] Print removed. specialized logger inside handler will capture it.
        raise_classified_http_exception(e, "Drive Proxy", user_id=current_user.email)

@router.get("/files/drive/monitored-folders")
async def get_monitored_folders(
    current_user: UserSchema = Depends(get_current_user)
):
    """
    [Sync Manager] Get details of all folders AND files currently being monitored (whitelisted).
    [Feature] Returns real sync status from DB.
    """
    if not current_user.monitored_folder_ids and not current_user.monitored_file_ids:
        return []
        
    # Lazy import to avoid circular dependency if any
    from app.services.drive_service import get_user_drive_service
    from app.utils.id_utils import to_internal_id 
    
    service = get_user_drive_service(current_user)
    monitored_list = []
    
    # 1. Folders
    for folder_id in current_user.monitored_folder_ids:
        try:
            # Fetch folder metadata
            folder_meta = service.files().get(
                fileId=folder_id,
                fields="id, name, webViewLink, iconLink, trashed",
                supportsAllDrives=True
            ).execute()
            
            # Fetch Real Sync Status (Folder Level)
            # Folder sync status is stored in 'system_status' collection
            status_doc = get_db().collection('system_status').document(folder_id).get()
            db_status = status_doc.to_dict() if status_doc.exists else {}
            
            last_synced = db_status.get("end_time") or db_status.get("start_time")
            if last_synced:
                last_synced = last_synced.isoformat() if hasattr(last_synced, 'isoformat') else str(last_synced)
            
            monitored_list.append({
                "id": folder_id,
                "name": folder_meta.get('name', 'Unknown Folder'),
                "link": folder_meta.get('webViewLink'),
                "type": "folder",
                "status": "active" if not folder_meta.get('trashed') else "trashed",
                "last_synced": last_synced
            })
            
        except Exception as e:
            monitored_list.append({
                "id": folder_id,
                "name": "Inaccessible Folder",
                "type": "folder",
                "status": "error",
                "error": str(e)
            })

    # 2. Files
    for file_id in (current_user.monitored_file_ids or []):
        try:
            # Fetch file metadata
            file_meta = service.files().get(
                fileId=file_id,
                fields="id, name, webViewLink, iconLink, trashed, mimeType",
                supportsAllDrives=True
            ).execute()
            
            # Fetch Real Sync Status (File Level)
            # File status is in 'files' collection
            internal_id = to_internal_id('fil_', file_id)
            file_doc = get_db().collection('files').document(internal_id).get()
            db_data = file_doc.to_dict() if file_doc.exists else {}
            
            updated_at = db_data.get("updatedAt") or db_data.get("created_at")
            if updated_at:
                updated_at = updated_at.isoformat() if hasattr(updated_at, 'isoformat') else str(updated_at)
            
            # Determine status
            status = "active"
            if file_meta.get('trashed'):
                status = "trashed"
            elif not file_doc.exists:
                status = "pending" # In list but not in DB yet
            
            monitored_list.append({
                "id": file_id,
                "name": file_meta.get('name', 'Unknown File'),
                "link": file_meta.get('webViewLink'),
                "type": "file",
                "mimeType": file_meta.get('mimeType'),
                "status": status,
                "last_synced": updated_at
            })
            
        except Exception as e:
            monitored_list.append({
                "id": file_id,
                "name": "Inaccessible File",
                "type": "file",
                "status": "error",
                "error": str(e)
            })    
            
    return monitored_list

@router.get("/files/{file_id}/sync-status")
async def get_file_sync_status(file_id: str, current_user: UserSchema = Depends(get_current_user)):
    """
    [Sync Manager] Check if a specific file or folder is already synced/ingested in our DB.
    Used for UI feedback (Action Card).
    """
    from app.utils.id_utils import to_internal_id
    
    # 1. Check if it's a file
    internal_id = to_internal_id('fil_', file_id)
    doc = get_db().collection('files').document(internal_id).get()
    
    if doc.exists:
        data = doc.to_dict()
        last_synced = data.get("updatedAt") or data.get("created_at")
        return {
            "exists": True,
            "type": "file",
            "last_synced": last_synced,
            "status": "synced"
        }
        
    # 2. Check if it's a folder (check system_status)
    status_doc = get_db().collection('system_status').document(file_id).get()
    if status_doc.exists:
        data = status_doc.to_dict()
        last_synced = data.get("end_time") or data.get("start_time")
        return {
            "exists": True,
            "type": "folder",
            "last_synced": last_synced,
            "status": data.get("status")
        }
        
    return {"exists": False, "status": "unknown"}

# 2. Virtual Tree API [DISABLED - Use /api/tree instead]
# @router.get("/files/virtual-tree")
# async def get_virtual_tree():
#     """
#     AI가 분류한 '가상 폴더 구조'를 트리 형태로 반환합니다.
#     Firestore에서 virtual_path 필드를 사용하여 계층 구조를 조립합니다.
#     (Real DB Use)
#     """
#     try:
#         docs = get_db().collection('files').stream()
        
#         tree = {"name": "Root", "children": [], "is_folder": True}
        
#         for doc in docs:
#             data = doc.to_dict()
#             v_path = data.get('virtual_path') 
            
#             if not v_path:
#                 continue
                
#             # 트리 구조 만들기 로직 (간소화)
#             current_node = tree
#             parts = v_path.strip("/").split("/")
            
#             for part in parts:
#                 found = False
#                 for child in current_node["children"]:
#                     if child["name"] == part and child.get("is_folder"):
#                         current_node = child
#                         found = True
#                         break
                
#                 if not found:
#                     new_node = {"name": part, "children": [], "is_folder": True}
#                     current_node["children"].append(new_node)
#                     current_node = new_node
            
#             # 리프 노드에 파일 추가
#             file_node = {
#                 "name": data.get('name'),
#                 "id": data.get('file_id'),
#                 "mime_type": data.get('mime_type'),
#                 "is_folder": False
#             }
#             current_node["children"].append(file_node)
            
#         return tree
        
#     except Exception as e:
#          raise HTTPException(status_code=500, detail=str(e))

# 3. File Detail & Logging (Real DB)
@router.get("/files/{file_id}")
async def get_file(
    file_id: str, 
    request: Request, 
    background_tasks: BackgroundTasks,
    current_user: UserSchema = Depends(get_current_user)
):

    """
    파일 상세 정보를 조회하고, 접근 로그를 남깁니다.
    """
    # 1. Real DB Query
    try:
        doc_ref = get_db().collection('files').document(file_id)
        doc = doc_ref.get()
        
        if not doc.exists:  
            
            # [Phase 4] 실패 로그 (404 Not Found)
            log_user_action(
                user=current_user,
                action=ActionType.VIEW,
                file_id=file_id,
                success=False,
                details={"error": "File not found"}
            )
            raise HTTPException(status_code=404, detail="File not found")
        
        file_info = doc.to_dict()
        # [Removed] file_dept_id logic
        
        # 2. Log Integration (Real Context)
        ip = request.client.host if request.client else None
        ua = request.headers.get("user-agent")
        
        # Background Task로 로그 저장
        background_tasks.add_task(
            log_user_action,
            user=current_user,
            action=ActionType.VIEW,
            file_id=file_id,
            success=True,
            ip_address=ip,
            details={"user_agent": ua}
        )
        
        return {"message": "File access success", "file": file_info}
        
    except Exception as e:
        if isinstance(e, HTTPException):
            raise e
            
        # [Phase 3] 예상치 못한 에러 로그
        # [Phase 4] 예상치 못한 에러 로그
        log_user_action(
            user=current_user,
            action=ActionType.VIEW,
            file_id=file_id,
            success=False,
            details={"error": str(e)}
        )
        raise e

@router.post("/files/{file_id}/download")
async def download_file(
    file_id: str, 
    request: Request, 
    background_tasks: BackgroundTasks,
    current_user: UserSchema = Depends(get_current_user)
):
    
    # [Log Integration] 다운로드 로그
    ip = request.client.host if request.client else None
    ua = request.headers.get("user-agent")
    
    # [Phase 3] 파일 정보 조회하여 부서 ID 확보 (DB 조회 Cost 추가됨)
    try:
        # doc = get_db().collection('files').document(file_id).get()  <-- DB 조회 불필요하면 제거 가능하지만, 파일 존재 체크용으로 둠
        
        background_tasks.add_task(
            log_user_action,
            user=current_user,
            action=ActionType.DOWNLOAD,
            file_id=file_id,
            success=True,
            ip_address=ip,
            details={"user_agent": ua}
        )
        
        return {"message": "Download started"}
        
    except Exception as e:
        log_user_action(
            user=current_user,
            action=ActionType.DOWNLOAD,
            file_id=file_id,
            success=False,
            details={"error": str(e)}
        )
        raise e