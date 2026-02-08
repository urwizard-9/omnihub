import json
import time
import logging
import io
import pandas as pd
from typing import Optional, Dict, Any, List

from google.cloud import storage
from google.cloud import firestore

# [통합] Backend Imports
from app.core.config import settings
from app.core.gcp_clients import get_firestore_client

# Logger
logger = logging.getLogger("ExcelExtractor")
logger.setLevel(logging.INFO)

class ExcelExtractor:
    def __init__(self):
        self.db = get_firestore_client()
        self.project_id = settings.PROJECT_ID
        self.bucket_name = getattr(settings, "GCS_BUCKET", f"{self.project_id}-docai-output")
        self.storage_client = storage.Client(project=self.project_id)
        self.bucket = self.storage_client.bucket(self.bucket_name)

    def process_single_document(self, file_id: str, gcs_uri: str, mime_type: str):
        """
        단일 Excel 문서에 대해 추출을 수행합니다.
        (Orchestrator에서 general_executor를 통해 호출됨)
        """
        logger.info(f"🚀 [Excel] 처리 시작: {file_id} ({mime_type})")

        try:
            # 1. GCS에서 파일 다운로드
            if not gcs_uri.startswith("gs://"):
                raise ValueError(f"Invalid GCS URI: {gcs_uri}")
            
            # [Fix] Parse bucket and path dynamically
            # gcs_uri: gs://bucket_name/path/to/obj
            parts = gcs_uri.replace("gs://", "").split("/", 1)
            if len(parts) != 2:
                raise ValueError(f"Invalid GCS URI format: {gcs_uri}")
                
            input_bucket_name = parts[0]
            input_blob_path = parts[1]
            
            input_bucket = self.storage_client.bucket(input_bucket_name)
            blob = input_bucket.blob(input_blob_path)
            file_bytes = blob.download_as_bytes()
            
            # 2. Pandas로 Excel 로드 (모든 시트)
            # engine='openpyxl' is safer for .xlsx
            all_sheets = pd.read_excel(io.BytesIO(file_bytes), sheet_name=None, engine='openpyxl')
            
            full_text_builder = ""
            pages = []
            
            # 3. 시트별 처리
            for idx, (sheet_name, df) in enumerate(all_sheets.items()):
                # Markdown 변환
                # fillna('') to avoid 'nan' in text
                markdown_text = df.fillna('').to_markdown(index=False)
                
                header = f"## Sheet: {sheet_name}\n\n"
                sheet_text = header + markdown_text + "\n\n"
                
                full_text_builder += sheet_text
                
                # 각 시트를 하나의 '페이지'로 취급
                pages.append({
                    "page_no": idx + 1,
                    "text": sheet_text,
                    "width": 0, # Excel doesn't have fixed dimensions
                    "height": 0
                })
                
            # 4. 결과 저장 경로 설정
            timestamp = int(time.time())
            output_prefix = f"docai_output/{file_id}/{timestamp}"
            output_filename = "excel_output.json"
            output_gcs_path = f"{output_prefix}/{output_filename}"
            output_gcs_uri = f"gs://{self.bucket_name}/{output_gcs_path}"
            
            # 5. 결과 JSON 생성
            result_artifact = {
                "full_text": full_text_builder,
                "pages": pages
            }
            
            # GCS 업로드
            out_blob = self.bucket.blob(output_gcs_path)
            out_blob.upload_from_string(
                json.dumps(result_artifact, ensure_ascii=False),
                content_type="application/json"
            )
            
            # 6. 최종 결과 DB 저장 (docai_results 컬렉션 호환)
            page_count = len(pages)
            
            result_doc = {
                "doc_id": file_id,
                "file_id": file_id,
                "full_text": full_text_builder,
                "pages": pages, # 구조 유지
                "status": "completed",
                "processed_at": firestore.SERVER_TIMESTAMP,
                "raw_output_uri": output_gcs_uri,
                "page_count": page_count,
                "processor_used": "pandas-excel-extractor"
            }
            
            self.db.collection("docai_results").document(file_id).set(result_doc, merge=True)
            
            # 원본 파일 상태 업데이트
            self.db.collection("files").document(file_id).set({
                "aiStatus": "completed",
                "pageCount": page_count
            }, merge=True)
            
            logger.info(f"✅ [Excel] 변환 완료: {file_id} (Sheets: {page_count})")

        except Exception as e:
            logger.error(f"❌ [Excel] 실패 ({file_id}): {e}", exc_info=True)
            self.db.collection("files").document(file_id).update({
                "aiStatus": "failed", 
                "errorMsg": str(e)
            })
            raise e
