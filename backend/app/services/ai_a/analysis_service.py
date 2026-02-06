import logging
import asyncio
from app.core.gcp_clients import get_firestore_client
from datetime import datetime

# [Adapter] Use existing RAG Orchestrator instead of missing PipelineRunner
from app.rag.orchestrator import orchestrator

# 로거 설정
logger = logging.getLogger("AnalysisService")
logger.setLevel(logging.INFO)

db = get_firestore_client()

async def trigger_analysis(file_id: str, gcs_uri: str, mime_type: str):
    """
    [Phase 3 Orchestrator Adapter]
    ingest.py에서 호출하는 인터페이스를 맞추되,
    실제 작업은 기존의 'app.rag.orchestrator'에게 위임합니다.
    """
    logger.info(f"⚡ [Pipeline Trigger] Wrapper started for {file_id}")

    # 1. 상태 업데이트 (Processing)
    # Orchestrator 내부에서도 상태 관리를 하지만, ingest.py가 기대하는 초기 상태를 세팅해줍니다.
    db.collection('files').document(file_id).update({
        "aiStatus": "processing",
        "aiStartedAt": datetime.utcnow()
    })

    try:
        # 3. PipelineRunner (AS-IS: Orchestrator) 실행
        # 기존 Orchestrator.run_pipeline은 async 함수이므로 바로 await 가능합니다.
        # 별도의 Thread/Process가 필요한 경우 Orchestrator 내부에서 처리하고 있습니다.
        
        await orchestrator.run_pipeline(file_id, gcs_uri, mime_type)
        
        # 4. 완료 처리
        # Orchestrator가 'pipeline_status'를 업데이트하겠지만, 
        # ingest.py가 기대하는 'aiStatus'도 맞춰줍니다.
        db.collection('files').document(file_id).update({
            "aiStatus": "completed",
            "aiCompletedAt": datetime.utcnow()
        })
        logger.info(f"✅ [Pipeline Trigger] Adapter execution completed for {file_id}")

    except Exception as e:
        logger.error(f"❌ [Pipeline Trigger] Adapter failed for {file_id}: {e}")
        
        # 1. Update File Status
        db.collection('files').document(file_id).update({
            "aiStatus": "failed",
            "errorMsg": str(e)
        })
        
        # 2. Log to System Errors (Dashboard)
        # [Pending] log_system_error not found in log_service.py. Using logger fallback.
        # import traceback
        # from app.services.log_service import log_system_error
        # log_system_error(...)
        logger.error(f"SYSTEM ERROR: AI Analysis Failed for {file_id}: {e}")
