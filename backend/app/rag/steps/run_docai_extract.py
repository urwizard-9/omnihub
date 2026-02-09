import json
import time
import logging
import re
from typing import Optional, Dict, Any, List

from google.api_core.client_options import ClientOptions
from google.cloud import documentai
from google.cloud import storage
from google.cloud import firestore

# [통합] Backend Imports
from app.core.config import settings
from app.core.gcp_clients import get_firestore_client

# 로거 설정
logger = logging.getLogger("DocAIService")
logger.setLevel(logging.INFO)

# 정적 매핑 정의
INVOICE_FIELD_MAP = {
    "invoice_id": ["invoice no", "invoice number", "inv #", "송장번호", "청구서번호"],
    "invoice_date": ["date", "invoice date", "issue date", "날짜", "일자", "발행일"],
    "total_amount": ["total", "amount due", "total amount", "grand total", "합계", "총액", "청구금액"],
    "tax_amount": ["tax", "vat", "surtax", "세액", "부가세"],
    "supplier_name": ["supplier", "vendor", "seller", "provider", "공급자", "판매자", "상호"],
    "receiver_name": ["receiver", "bill to", "buyer", "customer", "공급받는자", "구매자"],
    "currency": ["currency", "통화", "화폐"]
}

class DocAIExtractor:
    def __init__(self):
        self.db = get_firestore_client()
        self.project_id = settings.PROJECT_ID
        self.location = settings.DOC_AI_LOCATION
        self.bucket_name = getattr(settings, "GCS_BUCKET", f"{self.project_id}-docai-output")
        self.storage_client = storage.Client(project=self.project_id)
        self.bucket = self.storage_client.bucket(self.bucket_name)

        # DocAI Client
        api_endpoint = f"{self.location}-documentai.googleapis.com"
        client_options = ClientOptions(api_endpoint=api_endpoint)
        self.docai_client = documentai.DocumentProcessorServiceClient(client_options=client_options)

    # -------------------------------------------------------------------------
    # [CRITICAL] UTF-8 Byte Offset Handling
    # -------------------------------------------------------------------------
    def _get_text_from_anchor(self, text: str, text_anchor: dict) -> str:
        """
        Document AI는 startIndex/endIndex를 'Byte (UTF-8)' 기준으로 반환합니다.
        하지만 Python의 string 슬라이싱은 'Character' 기준입니다.
        
        따라서 한글(3 bytes)과 같은 멀티바이트 문자가 포함된 경우, 
        반드시 텍스트를 utf-8 바이트로 인코딩한 후 슬라이싱해야 정확한 글자를 가져올 수 있습니다.
        """
        if not text_anchor or "textSegments" not in text_anchor:
            return ""

        extracted_parts = []
        try:
            # 1. 텍스트를 UTF-8 바이트로 변환
            text_utf8 = text.encode("utf-8")
            
            for segment in text_anchor["textSegments"]:
                # 2. Byte Offset 기준으로 슬라이싱
                start_index = int(segment.get("startIndex", 0))
                end_index = int(segment.get("endIndex", len(text_utf8)))
                
                segment_bytes = text_utf8[start_index:end_index]
                
                # 3. 다시 문자열로 디코딩 (깨진 바이트 무시)
                extracted_parts.append(segment_bytes.decode("utf-8", errors="ignore"))
                
            return "".join(extracted_parts).strip()
            
        except Exception as e:
            logger.warning(f"Text extraction failed (encoding issue?): {e}")
            return ""

    def get_processor_name(self, mime_type: str) -> Optional[str]:
        proc_pdf = getattr(settings, "DOC_AI_PROCESSOR_ID_PDF", settings.DOCAI_PROCESSOR_ID)
        proc_img = getattr(settings, "DOC_AI_PROCESSOR_ID_IMAGE", settings.DOCAI_PROCESSOR_ID)
        
        processor_id = None
        if 'pdf' in mime_type.lower():
            processor_id = proc_pdf
        elif 'image' in mime_type.lower():
            processor_id = proc_img or proc_pdf
        
        if not processor_id:
            logger.warning(f"지원하지 않는 MIME Type: {mime_type}")
            return None
            
        return self.docai_client.processor_path(self.project_id, self.location, processor_id)

    def process_single_document(self, file_id: str, gcs_uri: str, mime_type: str) -> None:
        logger.info(f"🚀 [DocAI] 처리 시작: {file_id} ({mime_type})")
        
        processor_name = self.get_processor_name(mime_type)
        if not processor_name: 
            return

        try:
            timestamp = int(time.time())
            output_prefix = f"docai_output/{file_id}/{timestamp}"
            output_gcs_uri = f"gs://{self.bucket_name}/{output_prefix}"

            # Document AI Request Config
            input_config = documentai.BatchDocumentsInputConfig(
                gcs_documents=documentai.GcsDocuments(
                    documents=[documentai.GcsDocument(gcs_uri=gcs_uri, mime_type=mime_type)]
                )
            )
            output_config = documentai.DocumentOutputConfig(
                gcs_output_config=documentai.DocumentOutputConfig.GcsOutputConfig(gcs_uri=output_gcs_uri)
            )

            request = documentai.BatchProcessRequest(
                name=processor_name,
                input_documents=input_config,
                document_output_config=output_config,
            )

            logger.info(f" -> Google Cloud에 분석 요청 중... (Output: {output_gcs_uri})")
            operation = self.docai_client.batch_process_documents(request=request)
            
            # Wait for operation (Long-Running)
            operation.result(timeout=600) 
            logger.info(f" -> 분석 완료. 결과 수집 및 병합 중...")

            # Fetch & Merge (with Fixed Logic)
            merged_data = self.fetch_and_merge_results(output_prefix)
            
            # Extract Structured Fields
            extracted_entities = merged_data.get("entities", [])
            kv_pairs = merged_data.get("kv_pairs", [])
            tables = merged_data.get("tables", [])
            
            # Canonical Mapping (Invoice)
            invoice_fields = self.map_canonical_fields(extracted_entities, kv_pairs)

            page_count = len(merged_data.get("pages", []))
            
            # Final Result Document
            result_doc = {
                "doc_id": file_id,
                "source_type": "docai",
                "mime_type": mime_type,
                "extracted_at": firestore.SERVER_TIMESTAMP,
                
                # Full Text (Canonical from Shard 0)
                "full_text": merged_data.get("full_text", ""),
                
                # Structured Data
                "pages": merged_data.get("pages", []),
                "entities": extracted_entities,
                "kv_pairs": kv_pairs,
                "tables": tables,
                "invoice_fields": invoice_fields,
                
                "layout_available": bool(tables or kv_pairs),
                "raw_output_uri": output_gcs_uri,
                "processor_used": processor_name,
                "doc_page_count": page_count
            }
            
            # Firestore Update
            batch = self.db.batch()
            batch.set(self.db.collection("docai_results").document(file_id), result_doc, merge=True)
            batch.set(self.db.collection("files").document(file_id), {
                "aiStatus": "completed",
                "pageCount": page_count,
                "processedAt": firestore.SERVER_TIMESTAMP
            }, merge=True)
            batch.commit()
            
            logger.info(f"✅ [DocAI] 최종 완료: {file_id} (페이지: {page_count})")

        except Exception as e:
            logger.error(f"❌ [DocAI] 실패 ({file_id}): {e}", exc_info=True)
            self.db.collection("files").document(file_id).update({
                "aiStatus": "failed", 
                "errorMsg": str(e)
            })

    def map_canonical_fields(self, entities: List[Dict], kv_pairs: List[Dict]) -> Dict[str, Any]:
        """
        Map extracted entities and KV pairs to canonical invoice fields based on INVOICE_FIELD_MAP.
        Priority: Entities (High Confidence) > KV Pairs (Fallback)
        """
        canonical = {}
        
        # 1. Check CDE Entities
        for ent in entities:
            t = ent.get("type", "").lower()
            val = ent.get("normalized_value") or ent.get("mention")
            
            for canon_key, keywords in INVOICE_FIELD_MAP.items():
                if t == canon_key or t in keywords: # Exact type match preferred
                    if canon_key not in canonical:
                        canonical[canon_key] = val
        
        # 2. Check KV Pairs
        for kv in kv_pairs:
            k = kv.get("key", "").lower()
            v = kv.get("value", "")
            
            if not v: continue
            
            for canon_key, keywords in INVOICE_FIELD_MAP.items():
                if canon_key not in canonical:
                    # Partial match in key text
                    if any(kw in k for kw in keywords):
                        canonical[canon_key] = v
                        
        return canonical

    def fetch_and_merge_results(self, output_prefix: str) -> Dict[str, Any]:
        """
        Fetch all output shards from GCS and merge them intelligently.
        - Merges text from all pages in sequential order.
        - Converts tables to markdown and appends to full_text for complete context.
        - Decodes text using Byte Offsets for correct UTF-8 handling.
        """
        blobs = list(self.bucket.list_blobs(prefix=output_prefix))
        json_blobs = [b for b in blobs if b.name.endswith(".json")]
        
        # Sort shards to ensure order (results-1-of-2.json, etc.)
        try:
            json_blobs.sort(key=lambda x: int(re.search(r'-(\d+)-of-', x.name).group(1)) if re.search(r'-(\d+)-of-', x.name) else x.name)
        except:
             json_blobs.sort(key=lambda x: x.name)

        all_pages = []
        all_entities = []
        all_kv_pairs = []
        all_tables = []
        
        for i, blob in enumerate(json_blobs):
            try:
                content = blob.download_as_bytes()
                shard = json.loads(content)
                shard_text = shard.get("text", "")
                
                # --- Page processing ---
                for page in shard.get("pages", []):
                    page_no = page.get("pageNumber", 1)
                    dims = page.get("dimension", {})
                    
                    # Extract Page Text using Byte Offsets
                    page_text = ""
                    text_segments = page.get("layout", {}).get("textAnchor", {}).get("textSegments", [])
                    if text_segments:
                         page_text = self._get_text_from_anchor(shard_text, page.get("layout", {}).get("textAnchor", {}))

                    all_pages.append({
                        "page_no": page_no,
                        "text": page_text,
                        "width": dims.get("width"),
                        "height": dims.get("height")
                    })
                    
                    # Form Fields (KV)
                    for field in page.get("formFields", []):
                        key_anchor = field.get("fieldName", {}).get("textAnchor", {})
                        val_anchor = field.get("fieldValue", {}).get("textAnchor", {})
                        
                        key_text = self._get_text_from_anchor(shard_text, key_anchor)
                        val_text = self._get_text_from_anchor(shard_text, val_anchor)
                        
                        if key_text:
                            all_kv_pairs.append({
                                "key": key_text,
                                "value": val_text,
                                "confidence": field.get("confidence", 0.0),
                                "page_no": page_no
                            })

                    # Tables
                    for tbl in page.get("tables", []):
                        rows_data = []
                        # Header rows
                        for h_row in tbl.get("headerRows", []):
                            cells_data = []
                            for cell in h_row.get("cells", []):
                                c_anchor = cell.get("layout", {}).get("textAnchor", {})
                                c_text = self._get_text_from_anchor(shard_text, c_anchor)
                                cells_data.append(c_text)
                            rows_data.append({"cells": cells_data, "is_header": True})
                        # Body rows
                        for b_row in tbl.get("bodyRows", []):
                            cells_data = []
                            for cell in b_row.get("cells", []):
                                c_anchor = cell.get("layout", {}).get("textAnchor", {})
                                c_text = self._get_text_from_anchor(shard_text, c_anchor)
                                cells_data.append(c_text)
                            rows_data.append({"cells": cells_data, "is_header": False})
                            
                        all_tables.append({
                            "page_no": page_no,
                            "rows": rows_data,
                            "row_count": len(rows_data)
                        })

                # --- Entities (CDE) ---
                for ent in shard.get("entities", []):
                    ent_type = ent.get("type", "")
                    norm_val = ent.get("normalizedValue", {}).get("text")
                    
                    mention_anchor = ent.get("textAnchor", {})
                    mention_text = self._get_text_from_anchor(shard_text, mention_anchor)
                    if not mention_text:
                        mention_text = ent.get("mentionText", "")
                    
                    try:
                        p_ref = int(ent.get("pageAnchor", {}).get("pageRefs", [{}])[0].get("page", 0)) + 1
                    except:
                        p_ref = 1
                    
                    all_entities.append({
                        "type": ent_type,
                        "mention": mention_text,
                        "normalized_value": norm_val,
                        "confidence": ent.get("confidence", 0.0),
                        "page_no": p_ref
                    })

            except Exception as e:
                logger.error(f"Error processing shard {blob.name}: {e}")
                continue

        # Sort pages numerically
        all_pages.sort(key=lambda p: p['page_no'])
        
        # [FIX] Build full_text from ALL page texts (not just Shard 0)
        page_texts = [f"[Page {p['page_no']}]\n{p['text']}" for p in all_pages if p.get('text')]
        canonical_full_text = "\n\n".join(page_texts)
        
        # [FIX] Convert tables to markdown and append to full_text
        for tbl in all_tables:
            md_lines = [f"\n[Table on Page {tbl['page_no']}]"]
            for row in tbl.get("rows", []):
                cells = row.get("cells", [])
                if cells:
                    row_text = " | ".join([c.strip().replace('\n', ' ') for c in cells])
                    md_lines.append(row_text)
                    if row.get("is_header"):
                        md_lines.append("-" * (len(row_text) // 2))  # Markdown header separator
            canonical_full_text += "\n".join(md_lines) + "\n"
        
        return {
            "full_text": canonical_full_text,
            "pages": all_pages,
            "entities": all_entities,
            "kv_pairs": all_kv_pairs,
            "tables": all_tables
        }

if __name__ == "__main__":
    pass