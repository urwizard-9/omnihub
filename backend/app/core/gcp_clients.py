from google.cloud import firestore as google_firestore
from google.oauth2 import service_account
from googleapiclient.discovery import build
from app.core.config import settings

# Firestore 클라이언트 초기화
# Cloud Run 환경에서는 google.cloud.firestore.Client를 직접 사용하는 것이 더 안정적
db = None

# 명시적으로 프로젝트 ID와 데이터베이스 지정
PROJECT_ID = "jnu-rise-edu-150"
DATABASE_ID = "(default)"  # Firestore 데이터베이스 ID

def get_firestore_client():
    """
    Firestore 클라이언트를 반환합니다.
    프로젝트 ID와 데이터베이스 ID를 명시적으로 지정하여 올바른 Firestore에 연결합니다.
    """
    global db
    if db is None:
        try:
            # 항상 프로젝트 ID와 데이터베이스 ID를 명시적으로 지정
            if settings.GOOGLE_APPLICATION_CREDENTIALS:
                db = google_firestore.Client.from_service_account_json(
                    settings.GOOGLE_APPLICATION_CREDENTIALS,
                    project=PROJECT_ID,
                    database=DATABASE_ID
                )
                print(f"[INFO] Firestore client initialized with service account file, project={PROJECT_ID}, database={DATABASE_ID}")
            else:
                # Cloud Run에서 Application Default Credentials 사용
                db = google_firestore.Client(
                    project=PROJECT_ID,
                    database=DATABASE_ID
                )
                print(f"[INFO] Firestore client initialized with ADC, project={PROJECT_ID}, database={DATABASE_ID}")
        except Exception as e:
            print(f"[ERROR] Failed to initialize Firestore client: {e}")
            import traceback
            traceback.print_exc()
            raise
    return db

# 2. Google Drive API 클라이언트 초기화
SCOPES = ['https://www.googleapis.com/auth/drive.readonly']  # SCOPES 설명: Google API는 보안을 위해 앱이 어떤 권한(읽기 전용, 쓰기 가능 등)을 사용하는지 명시적으로 요구합니다.

def get_drive_service():
    """
    구글 드라이브 API 클라이언트를 생성하여 반환합니다.
    service_account.json 파일을 사용하여 인증합니다.
    """
    creds = None
    if settings.GOOGLE_APPLICATION_CREDENTIALS:
        creds = service_account.Credentials.from_service_account_file(
            settings.GOOGLE_APPLICATION_CREDENTIALS, 
            scopes=SCOPES
        )
    return build('drive', 'v3', credentials=creds)
