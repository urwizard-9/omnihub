import json
import httpx
import vertexai
from vertexai.generative_models import GenerativeModel
from app.core.config import settings
from app.core.gcp_clients import get_firestore_client
from app.models.risk import RiskData
import logging

# Logger Setup
logger = logging.getLogger(__name__)

async def handle_risk_event(doc_name_input: str):
    """
    Handles Firestore trigger events from Eventarc.
    
    Args:
        doc_name_input: The resource name of the document, typically from 'ce-subject' header.
                        e.g. projects/.../databases/(default)/documents/risk_users_latest/{userId}
    """
    try:
        # 1. Parse Document ID from Name
        if not doc_name_input:
            logger.info("No document name provided. Skipping.")
            return

        # Extract userId from the path
        # New format: documents/risk_users_latest/{userId}/history/{docId}
        # Old format: documents/risk_users_latest/{userId}
        path_parts = doc_name_input.split('/')
        
        # Find the index of 'risk_users_latest' and get the next segment as userId
        try:
            risk_index = path_parts.index('risk_users_latest')
            doc_id = path_parts[risk_index + 1]  # userId is right after 'risk_users_latest'
        except (ValueError, IndexError):
            logger.error(f"Invalid document path format: {doc_name_input}")
            return
        
        logger.info(f"Processing Event for User ID: {doc_id}")
        
        # 2. Fetch Latest State from history subcollection
        # Since parent documents are empty (ghost documents), we query the history subcollection
        db = get_firestore_client()
        history_ref = db.collection('risk_users_latest').document(doc_id).collection('history')
        
        # Get the latest history entry
        try:
            from google.cloud.firestore import Query as direction
            latest_query = history_ref.order_by('lastEventAt', direction=direction.DESCENDING).limit(1)
            latest_docs = list(latest_query.stream())
            logger.info(f"User {doc_id}: Found {len(latest_docs)} history documents")
        except Exception as index_err:
            # Fallback: If Firestore index missing, fetch all and sort in memory
            logger.warning(f"Firestore index missing for {doc_id}: {index_err}")
            logger.info(f"Attempting memory sort fallback for {doc_id}...")
            all_docs = list(history_ref.limit(20).stream())
            all_docs.sort(key=lambda d: d.to_dict().get('lastEventAt', ''), reverse=True)
            latest_docs = all_docs[:1] if all_docs else []
            logger.info(f"Fallback: Found {len(latest_docs)} documents for {doc_id}")
        
        if not latest_docs:
            logger.warning(f"No history found for user {doc_id}. Skipping notification.")
            return
            
        risk_data_dict = latest_docs[0].to_dict()
        if not risk_data_dict:
            logger.warning(f"Empty data for user {doc_id}. Skipping notification.")
            return

        # 3. Check Conditions (Both must be True)
        # Condition 1: defconMode == "ALERT" (uppercase)
        # Condition 2: stateChanged == True
        defcon_mode = risk_data_dict.get('defconMode', '')
        state_changed = risk_data_dict.get('stateChanged', False)
        
        logger.info(f"User {doc_id}: defconMode='{defcon_mode}', stateChanged={state_changed}")
        
        # Check defconMode (case-insensitive comparison with "ALERT")
        if defcon_mode.upper() != 'ALERT':
            logger.info(f"User {doc_id}: defconMode is '{defcon_mode}', not 'ALERT'. Skipping notification.")
            return
            
        # Check stateChanged
        if not state_changed:
            logger.info(f"User {doc_id}: stateChanged is False. Skipping notification.")
            return

        # 4. Both conditions satisfied - Generate AI Summary
        logger.info(f"User {doc_id}: Conditions met (ALERT + stateChanged). Generating AI summary...")
        ai_summary = await generate_ai_summary(risk_data_dict)
        
        # 5. Send to Google Chat
        await send_google_chat_notification(ai_summary)
        
        logger.info(f"Successfully processed and sent risk alert for user {doc_id}")

    except Exception as e:
        logger.error(f"Error handling risk event: {e}", exc_info=True)
        # Eventarc relies on 200 OK to acknowledge. If we fail, we might want to return 200 anyway to stop retries if it's a logic error.
        # But raising ensures error tracking.
        raise e

async def generate_ai_summary(risk_data: dict) -> str:
    """
    Uses Vertex AI Gemini to generate a summary report for the risk event.
    """
    try:
        vertexai.init(project=settings.PROJECT_ID, location=settings.VERTEX_LOCATION)
        model = GenerativeModel(settings.VERTEX_MODEL_NAME) # e.g. "gemini-1.5-flash-001"
        
        prompt = f"""
        You are a Cyber Security AI Analyst.
        Analyze the following 'Risk User Log' and write a concise, high-priority incident report for the Security Administrator in Korean.
        
        ### Context (Field Descriptions)
        - `riskScore` (0-100): User's risk score.
        - `defconMode` ("alert", etc): Risk state.
        - `eventRisk`: Risk score added by this specific event. (Calculation: (Base(reconError) + Add(Rule)) * Weight)
        - `eventType`: Type of event detected.
        - `lastEventAt`: Time of this event.
        - `metadata.userDownloads5m`: Download count in last 5 mins (Indicator of mass leakage).
        - `metadata.zPos`: Anomaly Z-Score.
        - `reconError`: Autoencoder reconstruction error (Anomaly metric, threshold: p95Threshold).
        - `gcs.generation`: File version ID.
        - `traceId`: Pipeline trace ID.
        
        ### Input Data (JSON)
        {json.dumps(risk_data, indent=2, default=str)}
        
        ### Output Format
        Please provide the response in Google Chat compatible markdown.
        Structure:
        1. **🚨 보안 경고: 고위험 감지** (Headline)
        2. **사용자**: [User ID]
        3. **위험도**: [riskScore] ([defconMode])
        4. **사건 요약**: [Explain WHAT happened based on eventType and eventRisk in 1-2 sentences in Korean]
        5. **핵심 지표**:
            - 다운로드(5분): [value]
            - 이상 징후 점수: [value] (ReconError / Threshold)
        6. **조치 권장**: [Brief recommendation in Korean]
        
        Keep it professional, urgent, and strictly based on facts provided.
        """
        
        response = await model.generate_content_async(prompt)
        return response.text
        
    except Exception as e:
        logger.error(f"Failed to generate AI summary: {e}")
        return f"🚨 **Security Alert** (AI Summary Failed)\n\nRaw Data: {risk_data}\nError: {str(e)}"

async def send_google_chat_notification(message_text: str):
    """
    Sends the text message to Google Chat via Webhook.
    """
    webhook_url = settings.GOOGLE_CHAT_WEBHOOK_URL
    if not webhook_url:
        logger.warning("GOOGLE_CHAT_WEBHOOK_URL is not set. Skipping notification.")
        return

    payload = {"text": message_text}
    
    async with httpx.AsyncClient() as client:
        response = await client.post(webhook_url, json=payload)
        response.raise_for_status()
