import uuid
import sys
from datetime import datetime
from app.core.gcp_clients import get_drive_service, get_firestore_client
from app.core.config import settings

def start_watching_drive(webhook_url: str = None, user_email: str = "admin@omnihub.ai", user_obj=None):
    """
    구글 드라이브에 Webhook 알림(Watch)을 신청합니다.
    - webhook_url: Cloud Run 등 외부에서 접근 가능한 HTTPS URL 필수
    - user_email: 알림을 처리할 주체 (이 유저의 Whitelist 규칙을 따름)
    - user_obj: UserSchema 객체 (있으면 이 유저의 권한으로 신청, 없으면 ADC 사용)
    """
    # [Fix] Smart Auth: Use User Credentials if provided
    if user_obj:
        from app.services.drive_service import get_user_drive_service
        print(f"[Watch] Using credentials for user: {user_email}")
        service = get_user_drive_service(user_obj)
    else:
        print("[Watch] Using Server ADC Credentials (Fallback)")
        service = get_drive_service()
    
    # URL이 없으면 설정이나 예시 값 사용 (실제 배포시는 필수)
    if not webhook_url:
        print("[Error] Webhook URL is required to start watching.")
        # 로컬 개발 시에는 ngrok 등을 써야 함
        return

    # 채널 ID 생성 (고유값)
    channel_id = str(uuid.uuid4())
    
    body = {
        "id": channel_id,
        "type": "web_hook",
        "address": webhook_url
    }
    
    try:
        # 드라이브 전체 감시 (StartPageToken 사용 추천하지만 여기선 전체)
        # 1. StartPageToken 가져오기 (필수 파라미터)
        # 전체 드라이브를 감시하려면 "어디서부터" 감시할지 기준점이 필요함
        # [Fix] SupportsAllDrives required for user context
        token_response = service.changes().getStartPageToken(supportsAllDrives=True).execute()
        start_page_token = token_response.get('startPageToken')
        print(f"Got StartPageToken: {start_page_token}")

        # 2. Watch 요청 Send (pageToken 필수)
        print(f"Requesting Watch to: {webhook_url} (Channel: {channel_id})")
        # [Fix] Add supportsAllDrives=True
        response = service.changes().watch(
            body=body, 
            pageToken=start_page_token,
            supportsAllDrives=True,
            includeItemsFromAllDrives=True
        ).execute()
        
        result = {
            'resource_id': response['resourceId'],
            'channel_id': channel_id,
            'expiration': response.get('expiration'), 
            'url': webhook_url,
            'user_email': user_email, # [Added] Connect to User Context
            'created_at': datetime.now()
        }

        # 3. 채널 정보를 DB에 저장 (나중에 stop() 할 때 필요)
        # [Fix] Store in 'watch_channels' so webhook can find it
        doc_ref = get_firestore_client().collection('watch_channels').document(channel_id)
        doc_ref.set(result, merge=True)
        
        # Backup in system for easy debugging
        get_firestore_client().collection('system').document('drive_channel_info').set(result, merge=True)
        
        print(f"Watch Started: {result}")
        return result
        
    except Exception as e:
        print(f"Failed to start watch: {str(e)}")
        # [Fix] Log full traceback
        import traceback
        traceback.print_exc()
        raise e

if __name__ == "__main__":
    # 사용법: python -m app.utils.drive_watch <WEBHOOK_URL> <USER_EMAIL>
    if len(sys.argv) < 2:
        print("Usage: python -m app.utils.drive_watch <WEBHOOK_URL> [USER_EMAIL]")
        print("Example: python -m app.utils.drive_watch https://your-backend.run.app/webhook/drive edu_150@iceu.kr")
    else:
        url = sys.argv[1]
        u_email = sys.argv[2] if len(sys.argv) > 2 else "edu_150@iceu.kr"
        print(f"Starting watch for URL: {url} (User: {u_email})...")
        start_watching_drive(webhook_url=url, user_email=u_email)
