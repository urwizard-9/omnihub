import logging
import os
import io
import json
from urllib.parse import quote
from fastapi import APIRouter, Request, HTTPException, Depends
from fastapi.responses import StreamingResponse
from google.cloud import storage
from google.auth.transport.requests import AuthorizedSession
from google.oauth2.credentials import Credentials
from google import auth
from app.services.firestore_repo import FirestoreRepo
from app.core.dependencies import get_current_user
from app.models.user import UserSchema, Department
from app.models.log import ActionType
from app.services.log_service import log_user_action
from app.core.config import settings

# [Optional] GCS Signed URL Service (Hybrid Approach)
from app.services.signed_url_service import SignedURLService

logger = logging.getLogger("DownloadAPI")
router = APIRouter(prefix="/api/docs", tags=["Download"])
signer = SignedURLService()
storage_client = storage.Client()

def parse_gcs_uri(gcs_uri: str):
    """gs://bucket/path/to/blob -> (bucket, path/to/blob)"""
    if not gcs_uri.startswith("gs://"):
        return None, None
    parts = gcs_uri[5:].split("/", 1)
    if len(parts) != 2:
        return None, None
    return parts[0], parts[1]

@router.get("/{doc_id}/download")
async def download_document(
    request: Request, 
    doc_id: str,
    current_user: UserSchema = Depends(get_current_user)
):
    # 1. 문서 조회
    mw_auth_ctx = getattr(request.state, "auth_ctx", None)
    tenant_id = getattr(mw_auth_ctx, "tenant_id", "default")
    engagement_id = getattr(mw_auth_ctx, "engagement_id", "default")

    class SimpleAuthContext:
        def __init__(self, user, t_id, e_id):
            self.user_id = user.user_id
            self.email = user.email
            self.role = user.role
            self.department_id = user.department_id
            self.tenant_id = t_id
            self.engagement_id = e_id

    auth_ctx = SimpleAuthContext(current_user, tenant_id, engagement_id)
    repo = FirestoreRepo(auth_ctx)
    
    doc = repo.get_document(doc_id)
    if not doc:
         logger.warning(f"Doc {doc_id} not found. Context: tenant={tenant_id}, eng={engagement_id}")
         raise HTTPException(status_code=404, detail="Document Not Found")

    # Name & MimeType
    title = doc.get("title") or doc.get("name") or "document"
    # [Fix] Do NOT modify extension yet. Wait until we know if it's Export or Media.
    filename = title 
    
    mime_type = doc.get("mime_type") or doc.get("mimeType") or ""
    gcs_uri = doc.get("gcs_uri") or doc.get("gcsUri")
    source_link = doc.get("source_link") or doc.get("webViewLink")

    # 2. Log Action (Initiated)
    log_user_action(
        user=current_user,
        action=ActionType.DOWNLOAD,
        file_id=doc_id,
        details={"title": filename}
    )
    logger.info(f"Download Initiated: {doc_id} by {current_user.email}")

    # ====================================================
    # Strategy 1: GCS Streaming (Best Performance)
    # ====================================================
    if gcs_uri:
        bucket_name, blob_name = parse_gcs_uri(gcs_uri)
        if bucket_name and blob_name:
            try:
                bucket = storage_client.bucket(bucket_name)
                blob = bucket.blob(blob_name)
                
                if blob.exists():
                    def iterfile():
                        with blob.open("rb") as f:
                            while chunk := f.read(1024 * 1024): # 1MB
                                yield chunk
                    
                    # [Fix] RFC 5987 Compliance
                    filename_encoded = quote(filename.encode('utf-8'))
                    headers = {
                        'Content-Disposition': f"attachment; filename*=UTF-8''{filename_encoded}",
                        'Content-Type': mime_type or "application/octet-stream"
                    }
                    if filename.endswith(".pdf"): headers['Content-Type'] = "application/pdf"
                    
                    logger.info(f"Streaming from GCS: {gcs_uri}")
                    return StreamingResponse(iterfile(), headers=headers)
                else:
                    logger.warning(f"GCS Blob not found: {gcs_uri}")
            except Exception as e:
                logger.error(f"GCS Stream Error: {e}")

    # ====================================================
    # Strategy 2: Drive API Proxy (User Authenticated)
    # ====================================================
    
    user_creds = None
    if current_user.google_access_token:
        try:
            user_creds = Credentials(
                token=current_user.google_access_token,
                refresh_token=current_user.google_refresh_token,
                token_uri="https://oauth2.googleapis.com/token",
                client_id=settings.GOOGLE_CLIENT_ID,
                client_secret=settings.GOOGLE_CLIENT_SECRET,
                scopes=['https://www.googleapis.com/auth/drive.readonly']
            )
        except Exception as e:
            logger.warning(f"Failed to create user credentials: {e}")

    drive_file_id = str(doc_id).replace("fil_", "")
    
    if user_creds and drive_file_id:
        try:
            authed_session = AuthorizedSession(user_creds)
            
            # [Fix] Priority: Media (Original) > Export (Converted)
            # This ensures images/PDFs are downloaded as-is, and only Google Docs are converted.
            
            media_url = f"https://www.googleapis.com/drive/v3/files/{drive_file_id}?alt=media"
            
            logger.info(f"Proxy Attempt 1 (Media): {media_url}")
            drive_resp = authed_session.get(media_url, stream=True)
            
            final_mode = "media"
            final_mime_type = mime_type
            
            # If Media fails (e.g. Google Doc), try Export
            if drive_resp.status_code != 200:
                error_msg = drive_resp.text
                if "fileNotDownloadable" in error_msg or "Export only supports" in error_msg or drive_resp.status_code == 403 or drive_resp.status_code == 400:
                     logger.warning(f"Media download failed ({drive_resp.status_code}), trying Export...")
                     
                     # Determine Export Mime Type
                     export_mime = "application/pdf" # Default
                     if "spreadsheet" in mime_type:
                         export_mime = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                     elif "presentation" in mime_type:
                         export_mime = "application/vnd.openxmlformats-officedocument.presentationml.presentation"
                     
                     export_url = f"https://www.googleapis.com/drive/v3/files/{drive_file_id}/export?mimeType={export_mime}"
                     
                     logger.info(f"Proxy Attempt 2 (Export): {export_url}")
                     drive_resp = authed_session.get(export_url, stream=True)
                     
                     final_mode = "export"
                     final_mime_type = export_mime

            # 3. Final Handling
            if drive_resp.status_code == 200:
                def iter_drive():
                    for chunk in drive_resp.iter_content(chunk_size=1024*1024):
                        if chunk: yield chunk
                
                # Fix Filename Extension for Exported Files
                final_filename = filename
                if final_mode == "export":
                    ext_map = {
                        "application/pdf": ".pdf",
                        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": ".xlsx",
                        "application/vnd.openxmlformats-officedocument.presentationml.presentation": ".pptx"
                    }
                    ext = ext_map.get(final_mime_type, "")
                    if ext and not final_filename.endswith(ext):
                        final_filename += ext
                
                # RFC 5987 Encoding
                filename_encoded = quote(final_filename.encode('utf-8'))
                
                # Use Content-Type from response if available, else guessed one
                content_type = drive_resp.headers.get("Content-Type") or final_mime_type or "application/octet-stream"
                
                headers = {
                    'Content-Disposition': f"attachment; filename*=UTF-8''{filename_encoded}",
                    'Content-Type': content_type
                }
                logger.info(f"Drive Proxy Success for {doc_id} (Mode: {final_mode})")
                return StreamingResponse(iter_drive(), headers=headers)
            else:
                logger.error(f"Drive API Proxy Failed Final: {drive_resp.status_code} - {drive_resp.text}")
                
        except Exception as e:
            logger.error(f"Drive Proxy Exception: {e}")

    # ====================================================
    # Strategy 3: Last Resort (WebView Link)
    # ====================================================
    
    logger.warning(f"Fallback to WebView Link for {doc_id}")
    
    if source_link:
        return {
            "method": "webview",
            "url": source_link,
            "filename": filename
        }

    raise HTTPException(status_code=404, detail="File content unavailable")
