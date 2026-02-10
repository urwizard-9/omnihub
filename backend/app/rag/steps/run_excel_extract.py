import os
import json
import logging
import tempfile
import pandas as pd
import numpy as np
from datetime import datetime
from typing import Dict, Any, List

from google.cloud import storage 
from google.cloud import firestore

# [통합] Backend Imports
from app.core.config import settings
from app.core.gcp_clients import get_firestore_client

logger = logging.getLogger("ExcelExtractor")
logger.setLevel(logging.INFO)

class ExcelExtractor:
    def __init__(self):
        self.db = get_firestore_client()
        self.project_id = settings.PROJECT_ID
        self.storage_client = storage.Client(project=self.project_id)
        
        # Settings for Protection
        self.max_rows_per_sheet = int(getattr(settings, "EXCEL_MAX_ROWS_PER_SHEET", 5000))
        self.max_total_rows = int(getattr(settings, "EXCEL_MAX_TOTAL_ROWS", 20000))

    def _sanitize_value(self, val):
        """JSON Serialization Safe Converter"""
        if pd.isna(val): return None
        if isinstance(val, (pd.Timestamp, datetime)):
            return val.isoformat()
        if isinstance(val, (int, float)):
            return val
        return str(val).strip()

    def process_single_document(self, file_id: str, gcs_uri: str = None, mime_type: str = None, **kwargs):
        """
        Process Excel file -> Standard docai_results schema with 'excel_struct'
        Downloads file from GCS. Uses provided gcs_uri or fetches from Firestore.
        Arguments:
            file_id: Document ID
            gcs_uri: Optional GCS URI (gs://...)
            mime_type: Optional MIME Type (ignored but accepted for compatibility)
        """
        logger.info(f"📊 [Excel] 구조 분석 시작: {file_id}")
        
        tmp_path = None
        try:
            # 1. Get GCS URI (if not provided)
            if not gcs_uri:
                doc_ref = self.db.collection("files").document(file_id).get()
                if not doc_ref.exists:
                    # If document doesn't exist yet, we can't proceed unless gcs_uri was passed.
                    # But here gcs_uri IS None.
                    raise ValueError(f"File not found in DB: {file_id}")
                
                file_data = doc_ref.to_dict()
                gcs_uri = file_data.get("gcsUri") or file_data.get("gcs_uri") or file_data.get("storagePath")
            
            if not gcs_uri:
                raise ValueError(f"GCS URI not found for file: {file_id}")

            # 2. Download to Temp File
            bucket_name = gcs_uri.replace("gs://", "").split("/")[0]
            blob_path = "/".join(gcs_uri.replace("gs://", "").split("/")[1:])
            
            bucket = self.storage_client.bucket(bucket_name)
            blob = bucket.blob(blob_path)
            
            fd, tmp_path = tempfile.mkstemp(suffix=".xlsx")
            os.close(fd)
            
            logger.info(f"  -> Downloading {blob_path} to {tmp_path}...")
            blob.download_to_filename(tmp_path)

            # 3. Read Excel
            xls = pd.read_excel(tmp_path, sheet_name=None)
            
            excel_struct = {
                "sheets": [],
                "extract_params": {
                    "max_rows_per_sheet": self.max_rows_per_sheet,
                    "max_total_rows": self.max_total_rows
                }
            }
            
            pages = [] 
            full_text_parts = []
            
            total_rows_processed = 0

            # 4. Analyze Each Sheet
            for sheet_idx, (sheet_name, df) in enumerate(xls.items()):
                # A. Basic Stats
                row_count, col_count = df.shape
                headers = list(df.columns.astype(str))
                
                # B. Build Table Data (with Limits)
                table_rows = []
                truncated = False
                
                # Limit Check
                limit = self.max_rows_per_sheet
                if total_rows_processed + row_count > self.max_total_rows:
                    limit = max(0, self.max_total_rows - total_rows_processed)
                    truncated = True
                
                effective_rows = df.head(limit)
                
                raw_records = effective_rows.to_dict(orient='records')
                
                for r_idx, record in enumerate(raw_records):
                    clean_record = {k: self._sanitize_value(v) for k, v in record.items() if not pd.isna(v)}
                    if clean_record: 
                        table_rows.append({
                            "row_index": r_idx + 2, 
                            "cells": clean_record
                        })
                
                total_rows_processed += len(table_rows)

                # C. Build Sheet Struct
                sheet_obj = {
                    "sheet_name": sheet_name,
                    "used_range": {"rows": row_count, "cols": col_count},
                    "header": headers,
                    "tables": [
                        {
                            "table_id": f"table_{sheet_idx}_0",
                            "header": headers,
                            "rows": table_rows,
                            "row_count": len(table_rows),
                            "truncated": truncated or (row_count > limit)
                        }
                    ]
                }
                excel_struct["sheets"].append(sheet_obj)
                
                # D. Build Fallback Text
                sheet_summary_text = f"## Sheet: {sheet_name}\n"
                sheet_summary_text += f"- Columns: {', '.join(headers)}\n"
                sheet_summary_text += f"- Stats: {row_count} rows, {col_count} columns\n"
                if table_rows:
                    sheet_summary_text += "- Preview (First 5 rows):\n"
                    # Using explicit loop for safe string conversion
                    for r in table_rows[:5]:
                        try:
                            line = json.dumps(r['cells'], ensure_ascii=False)
                        except:
                            line = str(r['cells'])
                        sheet_summary_text += f"  {line}\n"
                
                full_text_parts.append(sheet_summary_text)
                
                pages.append({
                    "page_no": sheet_idx + 1,
                    "sheet_name": sheet_name,
                    "text": sheet_summary_text,
                    "width": None, "height": None
                })
                
                if total_rows_processed >= self.max_total_rows:
                    logger.warning(f"⚠️ Max total rows limit reached ({self.max_total_rows}). Stopping extraction.")
                    break

            full_text = "\n\n".join(full_text_parts)

            # 5. Save to Firestore
            result_doc = {
                "doc_id": file_id,
                "source_type": "excel",
                "mime_type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                "extracted_at": firestore.SERVER_TIMESTAMP,
                
                "full_text": full_text,
                "pages": pages,
                "excel_struct": excel_struct,
                "doc_page_count": len(pages)
            }
            
            self.db.collection("docai_results").document(file_id).set(result_doc, merge=True)
            self.db.collection("files").document(file_id).set({
                "aiStatus": "completed",
                "pageCount": len(pages)
            }, merge=True)
            
            logger.info(f"✅ [Excel] 구조 저장 완료: {file_id} (Sheets: {len(pages)}, Rows: {total_rows_processed})")
            
        except Exception as e:
            logger.error(f"❌ [Excel] 처리 실패: {e}", exc_info=True)
            self.db.collection("files").document(file_id).update({
                "aiStatus": "failed",
                "errorMsg": str(e)
            })
        finally:
            # Cleanup Temp File
            if tmp_path and os.path.exists(tmp_path):
                try:
                    os.remove(tmp_path)
                except: pass

if __name__ == "__main__":
    pass
