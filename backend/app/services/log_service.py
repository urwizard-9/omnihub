from datetime import datetime
from typing import Optional, Dict, Any
# from app.core.gcp_clients import db # [Remapped]
from app.core.gcp_clients import get_firestore_client
from app.models.user import UserSchema
from app.models.log import LogSchema, ActionType

import uuid
try:
    from app.services.bq_service import stream_logs_to_bigquery # Added BQ Service
except ImportError:
    # [Safe Integration] Fallback if bq_service missing
    stream_logs_to_bigquery = None

# Collection Name
LOGS_COLLECTION = "logs"

# Lazy DB Client to avoid circular dep issues during import time
def get_db():
    return get_firestore_client()

def log_user_action(
    user: UserSchema,
    action: ActionType,
    file_id: str,
    success: bool = True,
    ip_address: Optional[str] = None,
    details: Optional[Dict[str, Any]] = None
):
    """
    [Pipeline A] 사용자 행동 로그를 Firestore 및 BigQuery에 적재합니다.
    """
    try:
        log_entry = LogSchema(
            # [Fix] Strict Schema for AI-B (Only designated fields)
            event_ts=datetime.utcnow(),
            
            user_id=user.user_id, 
            user_department_id=user.department_id,
            
            file_id=file_id,
            
            action_type=action.value # Int
        )
        
        # 1. Add to Firestore (Auto-ID)
        log_dict = log_entry.dict(by_alias=True)
        get_db().collection(LOGS_COLLECTION).add(log_dict)
        
        # 2. Add to BigQuery (Direct Stream)
        if stream_logs_to_bigquery:
            stream_logs_to_bigquery(log_dict)
        
    except Exception as e:
        # 로그 적재 실패가 메인 비즈니스 로직을 중단시키면 안 됨
        print(f"❌ [LogService Error] Failed to write log: {e}")
        
    except Exception as e:
        # 로그 적재 실패가 메인 로직을 방해하면 안 됨 -> 콘솔 출력만
        print(f"[LogService Error] Failed to write log: {e}")

def log_system_error(
    error_code: str,
    message: str,
    path: str,
    user_id: Optional[str] = None,
    trace_id: Optional[str] = None,
    stack_trace: Optional[str] = None
):
    """
    [Pipeline B] 시스템 에러 로그를 Firestore, BigQuery에 적재합니다.
    사용자 행동 로그와 달리, 원인 분석을 위한 Stack Trace 등을 포함합니다.
    [Update] BigQuery 적재 제외 (Firestore Only) - 추후 API로 대시보드 연동
    """
    try:
        error_entry = {
            "timestamp": datetime.utcnow(),
            "error_code": error_code,
            "message": message,
            "path": path,
            "user_id": user_id or "system",
            "trace_id": trace_id or str(uuid.uuid4()),
            "stack_trace": stack_trace
        }
        
        # 1. Add to Firestore (sys_errors/{date}/logs)
        today_str = datetime.utcnow().strftime("%Y-%m-%d")
        get_db().collection("sys_errors").document(today_str).collection("logs").add(error_entry)
        
        # 2. [Fix] Add to BigQuery (Enabled)
        if stream_logs_to_bigquery:
            # Re-format for flat BQ structure if needed, or just dump as JSON
            # Using the same LOGS_TABLE or a dedicated one?
            # To avoid schema conflict, we stick to the Generic 'audit_logs_raw_changelog' 
            # but usually System Errors go to a separate table. 
            # For simplicity in this Phase, we stream to the SAME table but marking 'operation' as 'ERROR'.
            
            # However, logic in bq_service expects 'log_data' dict.
            # We can reuse stream_logs_to_bigquery or call client direct.
            # Best to reuse stream_logs_to_bigquery but it streams to LOGS_TABLE.
            # Let's wrap it in a safe call.
            stream_logs_to_bigquery(error_entry)

    except Exception as e:
        # 시스템 에러 로깅 실패가 원본 에러를 덮으면 안 됨 -> 콘솔 출력만
        print(f"❌ [LogService Critical] Failed to log system error: {e}")
