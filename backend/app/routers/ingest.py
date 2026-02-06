from datetime import datetime # Added
from app.core.logger import log_system_event # Added [Checked: Exists]

from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from google.cloud import firestore # Added for ArrayUnion
from app.core.dependencies import get_current_user # [Fixed] app.dependencies -> app.core.dependencies
from app.models.user import UserSchema
from app.services.drive_service import stream_file_to_gcs, list_files_in_folder_recursive
# from app.services.docai_service import process_documents_batch # [Deprecated - Phase 3]

# [Integration Pending] Waiting for app/services/ai_a/analysis_service.py
from app.services.ai_a.analysis_service import trigger_analysis # [Phase 3] New Service

from app.services.ingestion_service import process_and_catalog_file
from app.services.log_service import log_user_action
from app.models.log import ActionType

# [Fixed] db global not found in new gcp_clients, utilizing get_firestore_client adapter
from app.core.gcp_clients import get_firestore_client
db = get_firestore_client() 

from pydantic import BaseModel
from typing import List, Any, Dict

"""
ingest.py는 외부 요청을 처리하는 **관문(Router)**으로서, 불필요한 기능은 없습니다. 각 API가 존재하는 명확한 이유가 있습니다.

POST /ingest: (단건 수집) "파일 하나만 콕 집어서 올릴 때" 씁니다. (예: Webhook 이벤트, UI에서 파일 하나 업로드)
POST /sync-folder: (대량 수집) "폴더 통째로 동기화할 때" 씁니다. 사용자가 UI에서 폴더를 선택하면 백그라운드에서 수백 개의 파일을 긁어옵니다.
GET /status/{folder_id}: (상태 확인) 폴더 동기화는 오래 걸리므로, 프론트엔드가 "지금 몇 개 했어?"라고 물어볼 때 씁니다.
POST /process/batch: (수동 트리거) 자동 트리거가 실패했거나, 개발자가 강제로 여러 파일을 다시 분석 돌릴 때 씁니다.
sync_folder_task: API는 아니지만, 핵심 일꾼함수입니다. 폴더 내 파일 목록을 뒤져서 하나씩 ingest 로직을 태웁니다.
"""

router = APIRouter(
    prefix="/drive",
    tags=["drive"],
    responses={404: {"description": "Not found"}},
)

# 요청 바디 모델 정의
class IngestRequest(BaseModel):
    file_id: str

class SyncFolderRequest(BaseModel):
    folder_id: str

class ProcessItem(BaseModel):
    file_id: str
    gcs_uri: str
    mime_type: str

class BatchProcessRequest(BaseModel):
    items: List[ProcessItem]

@router.post("/ingest")
async def ingest_drive_file(
    request: IngestRequest,
    background_tasks: BackgroundTasks, # Added
    current_user: UserSchema = Depends(get_current_user)
):
    """
    [Phase 2] 사용자의 구글 드라이브 파일을 GCS(Google Cloud Storage)로 스트리밍 전송합니다.
    [Refactoring] 공통 로직(process_and_catalog_file)을 사용하도록 변경됨.
    """
    # [Integration Active] Error Handling available
    from app.utils.error_handler import raise_classified_http_exception

    if not current_user.google_access_token:
        raise HTTPException(status_code=400, detail="User is not connected to Google Drive")
        
    try:
        # Refactored Logic
        # [Performance Fix] Offload blocking IO (Download/Upload) to thread pool
        # This prevents the event loop from being blocked by large file transfers.
        import asyncio
        loop = asyncio.get_running_loop()
        
        # Run blocking function in thread pool
        result = await loop.run_in_executor(
            None, 
            lambda: process_and_catalog_file(current_user, request.file_id)
        )
        
        # [Phase 3] Trigger AI Analysis
        if result.get("status") != "skipped":
            # [Integration Active] analysis_service is ready
            background_tasks.add_task(
                 trigger_analysis,
                 file_id=request.file_id,
                 gcs_uri=result.get("gcs_uri"),
                 mime_type=result.get("mime_type")
            )
            
        # [Privacy Guard] Whitelist File (Subscribe to updates)
        try:
            user_ref = db.collection('users').document(current_user.email)
            user_ref.update({
                "monitoredFileIds": firestore.ArrayUnion([request.file_id])
            })
        except Exception as e:
            print(f"[Privacy] Failed to whitelist file {request.file_id}: {e}")
            
        return {
            "status": "success",
            "message": "File streamed and AI analysis triggered.",
            "data": result
        }
    except Exception as e:
        raise_classified_http_exception(e, "Ingest Service", current_user.user_id if current_user else "unknown")

import asyncio

async def sync_folder_task(user: UserSchema, folder_id: str):
    """
    Background Task for Folder Sync
    [Optimized] Uses Asyncio Benchmark & Delta Sync
    """
    try:
        start_time = datetime.now()
        print(f"[Sync-Task] Starting background sync for {folder_id}")
        
        # 1. List Files (Sync execution in thread to avoid blocking)
        loop = asyncio.get_running_loop()
        all_files = await loop.run_in_executor(None, list_files_in_folder_recursive, user, folder_id)
        
        processed_count = 0
        skipped_count = 0 # Track skipped files
        failed_list = []
        # [System Status] Start Tracking
        # Preview first 5 files as queue
        initial_queue = [f['name'] for f in all_files[:5]]
        
        db.collection("system_status").document(folder_id).set({
            "status": "running",
            "start_time": start_time,
            "total_files": len(all_files),
            "processed": 0,
            "skipped": 0,
            "queue_preview": initial_queue,
            "recent_completed": []
        })

        print(f"[Sync-Task] Found {len(all_files)} files. Starting Batch Ingestion (Concurrency: 5)...")
        
        # 2. Batch Processing Setup
        semaphore = asyncio.Semaphore(5) # Limit concurrency to avoid OOM or Rate Limits

        async def process_wrapper(file_item):
            async with semaphore:
                try:
                    # [Optimization] Check abort only if we are seemingly running
                    status_doc = db.collection("system_status").document(folder_id).get()
                    if status_doc.exists and status_doc.to_dict().get("request_abort"):
                        return {"status": "cancelled", "file_item": file_item, "error": "User Cancelled"}

                    # Run sync blocking IO in thread pool
                    result = await loop.run_in_executor(
                        None,
                        lambda: process_and_catalog_file(
                            user, 
                            file_item['id'], 
                            virtual_path=file_item.get('virtual_path'),
                            drive_meta=file_item # Pass meta for Delta Check
                        )
                    )
                    return {"status": "success", "file_item": file_item, "result": result}
                except Exception as e:
                    return {"status": "error", "file_item": file_item, "error": str(e)}

        # 3. Execute concurrently
        tasks = [process_wrapper(item) for item in all_files]
        
        # 4. Monitor Progress
        recent_completed = [] # [Fix] Initialize locally
        
        for i, future in enumerate(asyncio.as_completed(tasks)):
            res = await future
            processed_count += 1
            
            completion_entry = {}
            
            if res["status"] == "success":
                f_item = res["file_item"]
                ingest_result = res["result"]
                
                status_label = "success"
                if ingest_result.get("status") == "skipped":
                    status_label = "skipped"
                    skipped_count += 1
                else:
                    # Trigger AI
                    if ingest_result.get("status") != "error":
                         file_id = f_item['id']
                         # [Integration Active]
                         asyncio.create_task(trigger_analysis(
                             file_id=file_id,
                             gcs_uri=ingest_result.get("gcs_uri"),
                             mime_type=ingest_result.get("mime_type")
                         ))
                         print(f"[Sync-Task] Triggered AI Analysis for {file_id}")

                completion_entry = {
                    "name": f_item['name'],
                    "status": status_label,
                    "timestamp": datetime.now().isoformat()
                }

            else:
                f_item = res["file_item"]
                print(f"[Sync-Task] Failed {f_item['name']} ({f_item['id']}): {res['error']}")
                failed_list.append({
                    "file_id": f_item['id'],
                    "name": f_item['name'],
                    "error": res['error']
                })
                completion_entry = {
                    "name": f_item['name'],
                    "status": "failed",
                    "error": str(res['error']),
                    "timestamp": datetime.now().isoformat()
                }
            
            # Update Recent History
            recent_completed.insert(0, completion_entry) # Prepend
            if len(recent_completed) > 5:
                recent_completed.pop()

            # Periodic Update (Every 5 files or last file)
            if processed_count % 5 == 0 or processed_count == len(all_files):
                # Calculate Queue Preview (Next 5 items from master list)
                next_batch_idx = processed_count
                queue_preview = [f['name'] for f in all_files[next_batch_idx : next_batch_idx + 5]]
                
                db.collection("system_status").document(folder_id).update({
                    "processed": processed_count,
                    "skipped": skipped_count,
                    "recent_completed": recent_completed,
                    "queue_preview": queue_preview
                })

        # Summary Log
        end_time = datetime.now()
        duration = (end_time - start_time).total_seconds()
        
        # [System Status] Complete Tracking
        db.collection("system_status").document(folder_id).update({
            "status": "completed",
            "end_time": end_time,
            "duration": duration,
            "processed": processed_count,
            "skipped": skipped_count,
            "failed": len(failed_list),
            "recent_completed": recent_completed,
            "queue_preview": [] # Clear queue
        })
        
        # [Enrichment] Richer Context
        details_payload = {
            "activity": "folder_sync_background",
            "folderId": folder_id,
            "totalFound": len(all_files),
            "processedCount": processed_count,
            "skippedCount": skipped_count, # Added
            "failedCount": len(failed_list),
            "durationSeconds": duration,
            "failedItems": failed_list[:10] 
        }

        log_user_action(
            user=user,
            action=ActionType.VIEW,
            file_id=folder_id,
            success=True,
            details=details_payload
        )
        
        # [System Log]
        log_system_event(
            event_type="SYNC_COMPLETED",
            component="IngestRouter",
            payload=details_payload
        )
        print(f"[Sync-Task] Completed. Total: {len(all_files)}, Skipped: {skipped_count}, Failed: {len(failed_list)}")

    except Exception as e:
        print(f"[Sync-Task] Critical Error: {e}")
        # 1. Mark as failed in DB
        db.collection("system_status").document(folder_id).set({
             "status": "failed",
             "error": str(e),
             "end_time": datetime.now()
        }, merge=True)
        
        # 2. Log to System Kernel Panic (Dashboard)
        import traceback
        from app.services.log_service import log_system_error
        log_system_error(
            error_code="SYNC_TASK_CRASH",
            message=f"Folder Sync Crashed for {folder_id}: {str(e)}",
            path="ingest.sync_folder_task",
            user_id=user.user_id,
            stack_trace=traceback.format_exc()
        )

@router.post("/sync-folder")
def sync_drive_folder(
    request: SyncFolderRequest,
    background_tasks: BackgroundTasks,
    current_user: UserSchema = Depends(get_current_user)
):
    """
    [Feature] Recursive Folder Sync (Background)
    지정된 폴더의 동기화 작업을 백그라운드에서 실행하고, 즉시 응답을 반환합니다.
    (Timeout 방지)
    """
    if not current_user.google_access_token:
        raise HTTPException(status_code=400, detail="User is not connected to Google Drive")

    # Start Background Task
    background_tasks.add_task(sync_folder_task, current_user, request.folder_id)

    # [Privacy Guard] Auto-whitelist this folder
    try:
        user_ref = db.collection('users').document(current_user.email)
        # Use ArrayUnion to append without reading first (Atomic)
        user_ref.update({
            "monitoredFolderIds": firestore.ArrayUnion([request.folder_id])
        })
        print(f"[Privacy] Whitelisted folder {request.folder_id} for {current_user.email}")
    except Exception as e:
        print(f"[Privacy] Failed to whitelist folder: {e}")

    return {
        "status": "accepted",
        "message": "Folder sync started in background.",
        "folder_id": request.folder_id
    }

@router.delete("/sync-folder")
def unsync_drive_folder(
    request: SyncFolderRequest = None, # Make optional to support query params vs body
    folder_id: str = None, # Query Param support
    abort: bool = False,
    current_user: UserSchema = Depends(get_current_user)
):
    """
    [Privacy Guard] 지정된 폴더를 Whitelist(동기화 대상)에서 제외합니다.
    [Feature] abort=True일 경우, 진행 중인 동기화 작업에 중단 신호를 보냅니다.
    """
    # Normalize ID (Support JSON body or Query Param)
    target_id = folder_id if folder_id else (request.folder_id if request else None)
    if not target_id:
        raise HTTPException(status_code=400, detail="Missing folder_id")
    try:
        user_ref = db.collection('users').document(current_user.email)
        
        # ArrayRemove: 배열에서 해당 요소만 안전하게 제거
        # [Fix] Remove from BOTH lists since we handle mixed items now
        # [Schema Fix] Target camelCase fields which are the source of truth
        user_ref.update({
            "monitoredFolderIds": firestore.ArrayRemove([target_id]),
            "monitoredFileIds": firestore.ArrayRemove([target_id])
        })
        
        # [Feature] Send Cancellation Signal
        if abort:
             db.collection("system_status").document(target_id).set({
                 "request_abort": True,
                 "status": "cancelling" # UI Feedback
             }, merge=True)
             print(f"[Sync-Control] Abort signal sent for {target_id}")

        # Log Action
        log_user_action(
            user=current_user,
            action=ActionType.DELETE, # 설정 삭제로 간주
            file_id=target_id,
            success=True,
            details={"activity": "remove_whitelist_item", "abort_requested": abort}
        )
        
        print(f"[Privacy] Un-whitelisted item {target_id} for {current_user.email}")
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to unsync folder: {str(e)}")

    return {
        "status": "success",
        "message": "Folder removed from whitelist.",
        "folder_id": request.folder_id
    }

@router.get("/status/{folder_id}")
def get_sync_status(folder_id: str, current_user: UserSchema = Depends(get_current_user)):
    """
    [Polling] Check Sync Status
    """
    doc = db.collection("system_status").document(folder_id).get()
    if not doc.exists:
        return {"status": "idle"}
    return doc.to_dict()

@router.post("/process/batch")
async def process_drive_files_batch(
    request: BatchProcessRequest,
    current_user: UserSchema = Depends(get_current_user)
):
    """
    [Phase 3 - Simplified] 다수의 GCS 파일에 대해 AI 분석을 비동기 요청합니다.
    (기존의 Synchronous Batch Processing을 대체하여 trigger_analysis를 반복 호출합니다.)
    """
    triggered_count = 0
    failed_count = 0
    summary = []

    for item in request.items:
        try:
            # [Integration Active]
            asyncio.create_task(trigger_analysis(
                file_id=item.file_id, 
                gcs_uri=item.gcs_uri, 
                mime_type=item.mime_type
            ))
            
            triggered_count += 1
            summary.append({"file_id": item.file_id, "status": "triggered"})
            
        except Exception as e:
            failed_count += 1
            summary.append({"file_id": item.file_id, "status": "failed", "error": str(e)})

    # [LogService] Process Batch Log
    log_user_action(
        user=current_user,
        action=ActionType.VIEW,
        file_id="batch_process_trigger",
        success=True,
        details={
            "total": len(request.items),
            "triggered": triggered_count,
            "failed": failed_count
        }
    )

    return {
        "status": "batch_triggered",
        "processed_count": triggered_count,
        "details": summary,
        "message": "AI analysis has been triggered in the background for selected files."
    }

@router.get("/debug/users")
def list_all_users_debug():
    """
    [DEBUG] List all users and their monitored items.
    WARNING: Public endpoint for debugging only. Remove in production.
    """
    try:
        users = db.collection('users').stream()
        results = []
        for u in users:
            data = u.to_dict()
            results.append({
                "doc_id": u.id,
                "email": data.get("email"),
                "monitored_folders": data.get("monitored_folder_ids", []),
                "monitored_files": data.get("monitored_file_ids", [])
            })
        return {"count": len(results), "users": results}
    except Exception as e:
        return {"error": str(e)}

@router.post("/debug/fix-schema")
def fix_user_schema_debug():
    """
    [DEBUG] Repair User Schema Inconsistency (Snake -> Camel Merge)
    """
    try:
        users = db.collection('users').stream()
        count = 0
        details = []
        
        for u in users:
            data = u.to_dict()
            ref = db.collection('users').document(u.id)
            updates = {}
            
            # 1. Folders
            snake_folders = data.get("monitored_folder_ids", [])
            camel_folders = data.get("monitoredFolderIds", [])
            
            # If snake has data, ensure it's in camel
            if snake_folders:
                new_camel = list(set(camel_folders + snake_folders))
                if len(new_camel) > len(camel_folders):
                    updates["monitoredFolderIds"] = new_camel
                # Delete snake key
                updates["monitored_folder_ids"] = firestore.DELETE_FIELD
                
            # 2. Files
            snake_files = data.get("monitored_file_ids", [])
            camel_files = data.get("monitoredFileIds", [])
            
            if snake_files:
                new_camel_files = list(set(camel_files + snake_files))
                if len(new_camel_files) > len(camel_files):
                    updates["monitoredFileIds"] = new_camel_files
                updates["monitored_file_ids"] = firestore.DELETE_FIELD

            if updates:
                ref.update(updates)
                count += 1
                details.append(f"Fixed {u.id}: {list(updates.keys())}")
                
        return {"status": "success", "fixed_count": count, "details": details}
    except Exception as e:
        return {"error": str(e)}
