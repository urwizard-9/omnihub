from fastapi import APIRouter, Request, Header, BackgroundTasks, Depends
# from app.core.gcp_clients import get_drive_service, db # [Remapped]
from app.core.gcp_clients import get_drive_service, get_firestore_client
from app.services.drive_service import get_user_drive_service, stream_file_to_gcs
from app.models.user import UserSchema
from app.core.dependencies import get_current_user
from app.models.file import FileSchema
from app.common.schemas import AIAnalysisRequest # [Fix] Use existing schema (AS-IS)
import datetime
from typing import Optional
from app.core.logger import log_system_event
from app.utils.id_utils import to_internal_id # [Fix] Centralized Utility
from app.services.ai_a.analysis_service import trigger_analysis # [Phase 3] Added # Added import
import asyncio
from app.services.ingestion_service import process_and_catalog_file

# Check for drive_watch util
try:
    from app.utils.drive_watch import start_watching_drive
except ImportError:
    start_watching_drive = None

router = APIRouter()

def get_db():
    return get_firestore_client()

async def chain_ingestion_and_ai(user, file_id, drive_meta=None):
    """
    [Phase 3] Wrapper to chain Ingestion -> AI Analysis
    """
    try:
        # 1. Ingestion (Sync function run in thread)
        loop = asyncio.get_running_loop()
        result = await loop.run_in_executor(None, lambda: process_and_catalog_file(user, file_id, drive_meta=drive_meta))
        
        # 2. Trigger AI if new
        if result.get("status") != "skipped":
            # GCS URI와 MimeType이 있어야 함
            if result.get("gcs_uri"):
                # [Fix] Must use internal ID for Analysis Service
                internal_file_id = to_internal_id('fil_', file_id)
                await trigger_analysis(
                    file_id=internal_file_id, 
                    gcs_uri=result.get("gcs_uri"), 
                    mime_type=result.get("mime_type")
                )
    except Exception as e:
        print(f"[Pipeline] Error chain for {file_id}: {e}")


# Firestore에서 마지막 동기화 토큰 관리 (서버 재시작시에도 유지되도록)
# [수정됨] 토큰 저장은 이제 사용자별로 동적으로 관리됩니다.

def get_page_token(user_email: str = "global"):
    doc_id = f'drive_sync_token_{user_email}'
    doc = get_db().collection('system').document(doc_id).get()
    if doc.exists:
        return doc.to_dict().get('token')
    return None

def save_page_token(token: str, user_email: str = "global"):
    doc_id = f'drive_sync_token_{user_email}'
    get_db().collection('system').document(doc_id).set({'token': token, 'updated_at': datetime.datetime.now()}, merge=True)

@router.post("/webhook/drive")
async def handle_drive_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
    x_goog_resource_state: str = Header(None),
    x_goog_channel_id: str = Header(None),
    x_goog_resource_id: str = Header(None)
):
    """
    구글 드라이브로부터 변경 알림(Push Notification)을 수신하는 API입니다.
    [Real-time] 변경된 파일만 즉시 처리합니다.
    [Privacy] Whitelist(monitored_folder_ids)에 포함된 폴더의 파일만 처리합니다.
    """
    print(f"[Webhook] Resource State: {x_goog_resource_state}, Channel ID: {x_goog_channel_id}")

    # 1. Sync 알림
    if x_goog_resource_state == "sync":
        print(f"Channel {x_goog_channel_id} synced successfully.")
        return {"status": "ok"}

    # 2. 변경 알림
    if x_goog_resource_state in ["add", "update", "trash", "change"]:
        # 2-1. 채널 ID로 유저 식별
        # [Optimization] Use Direct Lookup instead of Query
        channel_doc = get_db().collection('watch_channels').document(x_goog_channel_id).get()
        if not channel_doc.exists:
             channel_doc = None
        
        if not channel_doc:
            print(f"[Webhook] Unknown Channel ID: {x_goog_channel_id}. Ignoring.")
            return {"status": "unknown_channel"}
            
        channel_data = channel_doc.to_dict()
        user_email = channel_data.get('user_email')
        
        # 유저 객체 복원
        user_ref = get_db().collection('users').document(user_email)
        user_snap = user_ref.get()
        if not user_snap.exists:
            print(f"[Webhook] User {user_email} not found in Firestore. Ignoring.")
            return {"status": "user_not_found"}
            
        user = UserSchema(**user_snap.to_dict())
        # monitored_ids = user.monitored_folder_ids # [Moved to loop]
        
        # 2-2. Start Page Token 가져오기
        saved_token = get_page_token(user_email)
        
        try:
            drive_service = get_user_drive_service(user)
            
            # [Fix] Fallback: If no saved token, request fresh start token
            if not saved_token:
                print(f"[Webhook] No saved pageToken for {user_email}, requesting fresh startPageToken")
                token_response = drive_service.changes().getStartPageToken(supportsAllDrives=True).execute()
                saved_token = token_response.get('startPageToken')
                # Save it immediately to prevent re-fetching
                if saved_token:
                    save_page_token(saved_token, user_email)
            
            # 2-3. 변경사항 조회
            response = drive_service.changes().list(
                pageToken=saved_token,
                fields="newStartPageToken, nextPageToken, changes(fileId, removed, file(id, name, mimeType, modifiedTime, trashed, parents))",
                supportsAllDrives=True,
                includeItemsFromAllDrives=True
            ).execute()
            
            changes = response.get('changes', [])
            new_token = response.get('newStartPageToken')
            
            print(f"[Webhook] Detected {len(changes)} changes for {user_email}.")
            
            for change in changes:
                file_id = change.get('fileId')
                file_item = change.get('file')
                
                # [Privacy Guard] Whitelist Check
                # monitored_ids가 비어있으면(초기 상태) 일단 다 허용하거나, 다 막아야 함.
                # [Schema Fix] Use snake_case accessor (Pydantic loads from camelCase DB key automatically)
                monitored_folder_ids = user.monitored_folder_ids
                monitored_file_ids = user.monitored_file_ids or []
                
                # Check if we have ANY restrictions
                has_restrictions = bool(monitored_folder_ids or monitored_file_ids)

                if has_restrictions and file_item:
                    is_allowed = False
                    
                    # A. Direct File Check (Single File Monitoring)
                    if file_id in monitored_file_ids:
                        is_allowed = True
                    
                    # B. Folder Parent Check (Recursive Monitoring)
                    if not is_allowed and monitored_folder_ids:
                        # 1. 직계 부모 확인
                        file_parents = file_item.get('parents', [])
                        if any(pid in monitored_folder_ids for pid in file_parents):
                            is_allowed = True
                        
                        # 2. 조상 추적 (Ancestry Check) - Max 5 levels
                        if not is_allowed and file_parents:
                            current_pid = file_parents[0] 
                            for _ in range(5):
                                if current_pid in monitored_folder_ids:
                                    is_allowed = True
                                    break
                                try:
                                    # 부모의 부모 조회 (Cache 권장되지만, 빈도가 낮으므로 직접 호출)
                                    p_meta = drive_service.files().get(
                                        fileId=current_pid, fields="parents"
                                    ).execute()
                                    p_parents = p_meta.get('parents')
                                    if not p_parents: break
                                    current_pid = p_parents[0]
                                except:
                                    break
                    
                    if not is_allowed:
                        print(f"[Privacy] Blocked {file_id}: Not in monitored folders or files.")
                        continue # Skip this file
                
                # A. 파일 삭제
                if change.get('removed') or (file_item and file_item.get('trashed')):
                    print(f"[Webhook] File removed/trashed: {file_id}")
                    auth_fil_id = to_internal_id('fil_', file_id)
                    
                    # 1. Update File Status (State Sync)
                    get_db().collection('files').document(auth_fil_id).update({
                        "trashed": True, 
                        "status": "deleted",
                        "updatedAt": datetime.datetime.now()
                    })
                    
                    # 2. Log Action (Audit Trail)
                    action_type = ActionType.DELETE if change.get('removed') else ActionType.TRASH
                                        
                    # 로그를 남기기 위해선 User 정보가 필요 (user 객체는 상단에서 이미 로드됨)
                    from app.services.log_service import log_user_action
                    # ActionType imported at top-level or used from model
                    
                    log_user_action(
                        user=user,
                        action=action_type, # [Fix] Use Enum directly
                        file_id=file_id,
                        success=True,
                        details={
                            "method": "webhook_event",
                            "explicit_removal": change.get('removed', False)
                        }
                    )
                    continue
                
                # B. 파일 추가/수정
                if file_item:
                    print(f"[Webhook] Processing change: {file_item.get('name')} ({file_id})")
                    # from app.services.ingestion_service import process_and_catalog_file # Moved to top
                    
                    # [Phase 3] Use Chain Wrapper (Ingest -> AI)
                    background_tasks.add_task(
                        chain_ingestion_and_ai,
                        user=user,
                        file_id=file_id,
                        drive_meta=file_item
                    )

            # 2-4. 새로운 Page Token 저장
            if new_token:
                save_page_token(new_token, user_email)
                
        except Exception as e:
            print(f"[Webhook] Error processing changes: {e}")
            
    return {"status": "processed"}

async def process_drive_changes(channel_id: Optional[str] = None):
    """
    변경된 파일 목록을 조회하고 파이프라인(Sync -> Ingestion)을 실행합니다.
    channel_id를 통해 User를 식별하여, 그 유저의 권한으로 조회합니다.
    """
    print(f"[Debug] process_drive_changes 시작. 받은 Channel ID: {channel_id}")
    drive_service = None
    user_email = "global"
    
    user_obj = None # Initialize
    
    # 1. 사용자 식별 (Auto-Watch 지원)
    if channel_id:
        print(f"채널 ID 해결 중: {channel_id}")
        channel_doc = get_db().collection('watch_channels').document(channel_id).get()
        if channel_doc.exists:
            channel_data = channel_doc.to_dict()
            tgt_email = channel_data.get('user_email')
            
            # 사용자의 토큰 가져오기
            user_ref = get_db().collection('users').document(tgt_email).get()
            if user_ref.exists:
                user_obj = UserSchema(**user_ref.to_dict())
                try:
                    drive_service = get_user_drive_service(user_obj)
                    user_email = tgt_email
                    print(f"사용자로 처리 중: {user_email}")
                except Exception as e:
                    print(f"사용자 Drive 서비스 생성 실패: {e}")
        else:
            print("DB에서 채널 ID를 찾을 수 없습니다. 기본 서비스 계정으로 폴백합니다.")

    # 사용자를 찾지 못한 경우 서비스 계정 사용 (Fallback)
    if not drive_service:
        print("전역 서비스 계정을 사용하여 드라이브 접근.")
        drive_service = get_drive_service()
    
    # 2. 마지막 토큰 가져오기 (사용자별 분리)
    page_token = get_page_token(user_email)
    
    # 토큰이 없으면 최신 상태부터 시작 
    if not page_token:
         try:
             response = drive_service.changes().getStartPageToken().execute()
             page_token = response.get('startPageToken')
             print(f"새 StartPageToken 초기화 ({user_email}): {page_token}")
             save_page_token(page_token, user_email) # 초기 토큰 저장
         except Exception as e:
             print(f"StartPageToken 획득 실패: {e}")
             return

    # 3. 변경사항 리스트 조회 (Pagination)
    while page_token:
        try:
            results = drive_service.changes().list(
                pageToken=page_token,
                spaces='drive',
                # includeRemoved=True # 삭제된 파일도 추적하려면 필요 (기본값 True)
            ).execute()
        except Exception as e:
            print(f"변경사항 조회 실패 ({user_email}): {e}")
            break
            
        changes = results.get('changes', [])
        
        for change in changes:
            file_id = change.get('fileId')
            # [Phase 4] System Log: File Detected
            log_system_event(
                event_type="FILE_DETECTED",
                component="DriveWebhook",
                payload={"file_id": file_id, "user_email": user_email}
            )
            
            # 파이프라인 실행
            try:
                # [Phase 3] Unified Pipeline Execution
                if user_obj:
                    # process_and_catalog_file handles GCS streaming, DB sync, and AI handoff
                    # [Phase 3] Use Chain Wrapper (Awaitable)
                    await chain_ingestion_and_ai(
                        user=user_obj,
                        file_id=file_id,
                        drive_meta=change.get('file')
                    )
                else:
                    print(f"[Skipped] {file_id}: User context missing (Global Sync not supported in Phase 3).")

            except Exception as e:
                print(f"파일 처리 실패 {file_id}: {e}")
                # 에러 발생 시 상태 업데이트
                get_db().collection('files').document(file_id).set({"aiStatus": "failed", "errorMsg": str(e)}, merge=True)

        if 'newStartPageToken' in results:
            # 더 이상 변경사항이 없으면 newStartPageToken을 저장하고 종료
            save_page_token(results.get('newStartPageToken'), user_email)
            break
        
        # 다음 페이지가 있으면 계속 조회
        page_token = results.get('nextPageToken')
        save_page_token(page_token, user_email) # 중간 저장

# === Admin / Setup API ===
from pydantic import BaseModel

class WatchRequest(BaseModel):
    webhook_url: str

@router.post("/drive/watch")
async def enable_drive_watch(body: WatchRequest):
    """
    [Admin] 구글 드라이브 변경 알림(Watch)을 시작합니다.
    - Cloud Run 배포 후, 해당 서버의 Webhook URL을 등록해야 합니다.
    """
    if not start_watching_drive:
        return {"status": "error", "message": "Module 'drive_watch' not available"}

    try:
        result = start_watching_drive(webhook_url=body.webhook_url)
        return {"status": "success", "info": result}
    except Exception as e:
        return {"status": "error", "message": str(e)}

@router.post("/drive/watch/renew-all")
async def renew_all_channels():
    """
    [Automation] 모든 활성 채널을 검사하고 만료가 임박한 채널을 갱신합니다.
    - Cloud Scheduler가 주기적으로 호출합니다.
    - 각 채널의 user_email을 확인하여, 해당 유저의 권한(Token)으로 갱신을 수행합니다.
    """
    if not start_watching_drive:
        return {"status": "error", "message": "Module 'drive_watch' not available"}

    try:
        channels = get_db().collection('watch_channels').stream()
        results = []
        
        for ch in channels:
            data = ch.to_dict()
            channel_id = ch.id
            user_email = data.get('user_email')
            webhook_url = data.get('url')
            
            # [Validation] 필수 데이터 확인
            if not user_email or not webhook_url:
                print(f"[Renew] Skipping invalid channel {channel_id}: Missing email or url")
                continue
                
            print(f"[Renew] Renewing channel for {user_email}...")
            
            # 1. User Load
            user_ref = get_db().collection('users').document(user_email).get()
            if not user_ref.exists:
                print(f"[Renew] Skipping {user_email}: User not found")
                continue
                
            user_obj = UserSchema(**user_ref.to_dict())
            
            # 2. Refresh Watch (New Channel)
            # 기존 채널을 중지(Stop)하는 로직은 복잡하므로, 일단 새 채널을 생성합니다.
            # (구글은 다중 채널을 허용하며, 오래된 것은 자동 만료됩니다.)
            try:
                new_channel = start_watching_drive(
                    webhook_url=webhook_url, 
                    user_email=user_email,
                    user_obj=user_obj # [Important] Use User Credentials
                )
                
                results.append({
                    "user": user_email,
                    "status": "renewed",
                    "new_channel_id": new_channel.get('channel_id')
                })
                
                # 3. Clean up OLD channel info from DB (Optional)
                # get_db().collection('watch_channels').document(channel_id).delete()
                # [Note] Keep history or mark as expired? For now, just leave it.
                
            except Exception as w_err:
                print(f"[Renew] Failed for {user_email}: {w_err}")
                results.append({"user": user_email, "status": "failed", "error": str(w_err)})
                
        return {"status": "completed", "results": results}
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        return {"status": "error", "message": str(e)}

@router.post("/drive/watch/register")
async def register_user_watch(
    current_user: UserSchema = Depends(get_current_user)
):
    """
    [Self-Service] 현재 로그인한 유저의 드라이브에 Webhook을 등록합니다.
    - Frontend에서 "Auto-Sync 활성화" 버튼 클릭 시 호출됩니다.
    """
    if not start_watching_drive:
        return {"status": "error", "message": "Module 'drive_watch' not available"}

    try:
        # [Config] Use the Service URL as Webhook Base
        # Note: In production, this should be env var or determined dynamically.
        # For Cloud Run, we use the host from config or hardcode the known URL pattern for this deployment.
        webhook_base = "https://omnihub-backend-707724932002.asia-northeast3.run.app"
        webhook_url = f"{webhook_base}/webhook/drive"
        
        print(f"[Register] Registering watch for {current_user.email}...")
        
        result = start_watching_drive(
            webhook_url=webhook_url,
            user_email=current_user.email,
            user_obj=current_user # [Important] Use User Context
        )
        
        return {"status": "success", "info": result}
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        return {"status": "error", "message": str(e)}
