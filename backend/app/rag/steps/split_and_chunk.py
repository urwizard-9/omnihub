import os
import json
import logging
import time
import re
from datetime import datetime
from typing import Dict, Any, List, Optional

from google.cloud import storage
from google.cloud import firestore

# [통합] Backend Imports
from app.core.config import settings
from app.core.gcp_clients import get_firestore_client

# Logger
logger = logging.getLogger("DocChunker")
logger.setLevel(logging.INFO)

class DocChunker:
    def __init__(self):
        self.db = get_firestore_client()
        self.project_id = settings.PROJECT_ID
        self.bucket_name = getattr(settings, "GCS_BUCKET", f"{self.project_id}-docai-output")
        self.bucket = storage.Client(project=self.project_id).bucket(self.bucket_name)
        
        # Base Config
        self.chunk_size = int(getattr(settings, "CHUNK_SIZE_HINT", 1000))
        self.chunk_overlap = int(getattr(settings, "CHUNK_OVERLAP_HINT", 200))
        
        # Ranking & Cap
        self.per_doc_cap = int(getattr(settings, "PER_DOC_CHUNK_CAP", 0)) # 0: No Limit
        self.enable_ranking = getattr(settings, "ENABLE_CHUNK_RANKING", "true").lower() == "true"
        self.section_target_size = int(self.chunk_size * 0.8)
        
        # Advanced Config
        self.excel_row_chunk_topn = int(getattr(settings, "EXCEL_ROW_CHUNK_TOPN", 50))
        self.use_section_chunking = getattr(settings, "USE_SECTION_CHUNKING", "true").lower() == "true"
        self.summary_max_chars = int(getattr(settings, "SUMMARY_MAX_CHARS", 2000))
        
        # Top Chunk Cache
        self.enable_top_chunk_cache = getattr(settings, "ENABLE_TOP_CHUNK_CACHE", "false").lower() == "true"
        self.top_chunk_cache_k = int(getattr(settings, "TOP_CHUNK_CACHE_K", self.per_doc_cap if self.per_doc_cap > 0 else 3))
        self.top_chunk_cache_max_chars = int(getattr(settings, "TOP_CHUNK_CACHE_MAX_CHARS", 2000))

        self.version = "v6.0-normalized-cache"

    # --- 0. Helper: Normalization & Serialization ---
    def normalize_value(self, val: Any) -> str:
        if val is None: return ""
        s_val = str(val).strip()
        
        # 1,234,567 -> 1234567
        if re.match(r'^-?[\d,]+(\.\d+)?$', s_val):
            if ',' in s_val:
                try:
                    num_val = float(s_val.replace(',', ''))
                    if num_val.is_integer():
                        return str(int(num_val))
                    return str(num_val)
                except:
                    pass
        
        # Date (YYYY.MM.DD or YYYY/MM/DD -> YYYY-MM-DD)
        date_pattern = r'(\d{4})[\./-](\d{1,2})[\./-](\d{1,2})'
        match = re.search(date_pattern, s_val)
        if match:
            y, m, d = match.groups()
            return f"{y}-{m.zfill(2)}-{d.zfill(2)}"
            
        return s_val

    def serialize_kv_pair(self, key: str, value: Any) -> str:
        norm_val = self.normalize_value(value)
        return f"{key}: {norm_val}"

    # --- Strategy Routing ---
    def get_chunking_strategy(self, 
                              profile_data: Dict[str, Any], 
                              docai_result: Dict[str, Any], 
                              app_config: Any) -> str:
        source_type = docai_result.get("source_type", "docai")
        if source_type == "excel" or docai_result.get("excel_struct"):
            return "excel"
        if docai_result.get("invoice_fields") or docai_result.get("kv_pairs"):
            return "invoice_ocr"
        return "text"

    # --- 1. Heuristic Summary ---
    def generate_heuristic_summary(self, full_text: str, doc_title: str) -> Dict[str, Any]:
        lines = full_text.split('\n')
        summary_lines = [f"# Document Summary: {doc_title}"]
        
        count = 0
        for line in lines:
            if not line.strip(): continue
            summary_lines.append(line.strip())
            count += 1
            if count >= 10: break
            
        if len(lines) > 10: summary_lines.append("\n... (Key Sections) ...\n")
        
        header_pattern = r'^\s*(?:第?\d+[조\.]|(?:\d+\))|(?:\(\d+\))|[가-하]\.|\[.+\]|Article\s+\d+|붙임|참고|주석).+'
        keywords = ["합계", "total", "결론", "책임", "조건", "기한", "금액", "지급", "세액", "vat", "총액"]
        
        captured = 0
        for line in lines[10:]:
            line = line.strip()
            if not line: continue
            
            if re.match(header_pattern, line) or any(kw in line.lower() for kw in keywords):
                summary_lines.append(line)
                captured += 1
                
            if len("\n".join(summary_lines)) > self.summary_max_chars:
                summary_lines.append("... (truncated)")
                break
                
        return {
            "text": "\n".join(summary_lines),
            "type": "doc_summary",
            "metadata": {"method": "heuristic", "captured": captured}
        }

    # --- 2. Section Aware Chunking ---
    def section_aware_text_chunking(self, text: str, target_size: int, overlap: int) -> List[Dict[str, Any]]:
        split_pattern = r'(\n\s*(?:第?\d+[조\.]|(?:\d+\))|(?:\(\d+\))|[가-하]\.|\[.+\]|Article\s+\d+).*|\n{2,})'
        
        if len(text) < target_size:
            return [{"text": text, "start_char_idx": 0, "end_char_idx": len(text), "type": "text_section"}]

        segments = re.split(split_pattern, text)
        chunks = []
        current_chunk_text = ""
        current_start_idx = 0
        current_has_header = False
        current_header_text = "" 
        
        idx = 0
        while idx < len(segments):
            segment = segments[idx]
            
            header_match = re.match(r'^\s*(?:第?\d+[조\.]|\[.+\]|Article.+)', segment.strip())
            if header_match:
                current_has_header = True
                current_header_text = segment.strip()[:50] 
            
            if len(current_chunk_text) + len(segment) > target_size and len(current_chunk_text) > 50:
                chunks.append({
                    "text": current_chunk_text,
                    "start_char_idx": current_start_idx,
                    "end_char_idx": current_start_idx + len(current_chunk_text),
                    "type": "text_section",
                    "metadata": {"has_header": current_has_header, "header": current_header_text} 
                })
                
                current_start_idx += len(current_chunk_text)
                current_chunk_text = ""
                if current_header_text:
                     if not header_match:
                         current_chunk_text += f"[{current_header_text} (cont.)]\n"

            current_chunk_text += segment
            idx += 1
            
        if current_chunk_text:
            chunks.append({
                "text": current_chunk_text,
                "start_char_idx": current_start_idx,
                "end_char_idx": current_start_idx + len(current_chunk_text),
                "type": "text_section",
                "metadata": {"has_header": current_has_header}
            })
            
        return chunks

    # --- 3. Naive Text (with Sentence Boundary Detection) ---
    def _find_sentence_boundary(self, text: str, target_idx: int, search_range: int = 100) -> int:
        """문장 경계(.다, .요, .함 등)를 찾아서 청크가 문장 중간에서 끊기지 않도록 함"""
        if target_idx >= len(text):
            return len(text)
        
        # 탐색 범위: target_idx 앞뒤 search_range 글자
        start = max(0, target_idx - search_range)
        end = min(len(text), target_idx + search_range)
        search_text = text[start:end]
        
        # 한국어 문장 종결 패턴
        sentence_endings = ['. ', '다. ', '요. ', '함. ', '음. ', '임. ', '.\n', '다.\n', '?\n', '!\n']
        
        best_pos = target_idx
        min_distance = search_range + 1
        
        for ending in sentence_endings:
            idx = search_text.find(ending)
            while idx != -1:
                abs_pos = start + idx + len(ending)
                distance = abs(abs_pos - target_idx)
                if distance < min_distance:
                    min_distance = distance
                    best_pos = abs_pos
                idx = search_text.find(ending, idx + 1)
        
        return best_pos

    def naive_text_chunking(self, text: str, size: int, overlap: int) -> List[Dict[str, Any]]:
        chunks = []
        if not text: return chunks
        length = len(text)
        start = 0
        while start < length:
            target_end = min(start + size, length)
            
            # 문장 경계에서 끊기
            if target_end < length:
                end = self._find_sentence_boundary(text, target_end)
            else:
                end = length
            
            chunk_text = text[start:end]
            if len(chunk_text) < 50 and start > 0: 
                pass  # skip very small trailing chunks
            else:
                chunks.append({
                    "text": chunk_text,
                    "start_char_idx": start,
                    "end_char_idx": end,
                    "type": "text_naive"
                })
            if end >= length: break
            start = max(start + 1, end - overlap)  # Ensure progress
        return chunks

    # --- 4. Excel Logic ---
    def excel_chunking_logic(self, docai_result: Dict[str, Any]) -> List[Dict[str, Any]]:
        chunks = []
        excel_struct = docai_result.get("excel_struct", {})
        sheets = excel_struct.get("sheets", [])
        
        summary = ["# Excel Summary"]
        summary.append(f"Total Sheets: {len(sheets)}")
        key_rows = []
        keywords = ["합계", "total", "sum", "결산", "잔액", "amount", "price", "계", "지급"]
        
        for sheet in sheets:
            s_name = sheet.get("sheet_name", "Sheet")
            row_cnt = sheet.get("used_range", {}).get("rows", 0)
            summary.append(f"\n## Sheet: {s_name} ({row_cnt} rows)")
            
            for tbl in sheet.get("tables", []):
                rows = tbl.get("rows", [])
                if rows:
                    for r in rows[:3]:
                        row_raw = " | ".join([self.serialize_kv_pair(k, v) for k,v in list(r.get("cells",{}).items())[:5]])
                        summary.append(f"  Row {r['row_index']}: {row_raw}")
                
                for r in rows:
                    cells = r.get("cells", {})
                    is_imp = any(any(kw in str(k).lower() or kw in str(v).lower() for kw in keywords) for k,v in cells.items())
                    
                    if is_imp:
                        row_fmt = " | ".join([self.serialize_kv_pair(k, v) for k,v in cells.items() if v])
                        key_rows.append(f"[{s_name}] Row {r['row_index']}: {row_fmt}")

        chunks.append({"text": "\n".join(summary), "type": "excel_summary"})
        if key_rows:
            limit = self.excel_row_chunk_topn
            c_text = "\n".join(key_rows[:limit])
            if len(key_rows) > limit: c_text += f"\n... ({len(key_rows)-limit} more)"
            chunks.append({"text": c_text, "type": "excel_row"})
        return chunks

    # --- 5. Invoice Logic ---
    def invoice_chunking_logic(self, docai_result: Dict[str, Any]) -> List[Dict[str, Any]]:
        chunks = []
        inv_fields = docai_result.get("invoice_fields", {})
        kv_pairs = docai_result.get("kv_pairs", [])
        entities = docai_result.get("entities", [])
        
        kv_lines = ["# Invoice Summary"]
        
        if inv_fields:
            kv_lines.append("\n## Canonical Fields:")
            for k, v in inv_fields.items():
                kv_lines.append(f"- {self.serialize_kv_pair(k, v)}")
        
        if entities:
            for ent in entities:
                if ent.get("confidence", 0) > 0.6:
                     # ent.get("mention") can be None
                    val = ent.get("mention") or ""
                    kv_lines.append(f"- {ent.get('type')}: {self.normalize_value(val)}")
        
        chunks.append({"text": "\n".join(kv_lines), "type": "invoice_kv"})
        
        tables = docai_result.get("tables", [])
        table_lines = ["# Line Items"]
        if tables:
            for i, tbl in enumerate(tables):
                table_lines.append(f"\n## Table {i+1}")
                rows = tbl.get("rows", [])
                for idx, r in enumerate(rows):
                    cells = r.get("cells", [])
                    norm_cells = [self.normalize_value(c) for c in cells]
                    table_lines.append(f"Row {idx+1}: {' | '.join(norm_cells)}")
        else:
            full_text = docai_result.get("full_text", "")
            lines = full_text.split('\n')
            for line in lines:
                if any(c.isdigit() for c in line) and len(line) > 10:
                    table_lines.append(line.strip())
        
        chunks.append({"text": "\n".join(table_lines[:100]), "type": "line_items"})
        return chunks

    # --- 6. Ranking System ---
    def calculate_chunk_score(self, chunk: Dict[str, Any], doc_context: Dict[str, Any]) -> tuple:
        score = 0.0
        reasons = []
        c_type = chunk.get("type", "text")
        
        base_map = {
            "doc_summary": 100, "idp_summary": 100, "kv_summary": 100, "invoice_kv": 98,
            "excel_summary": 95, "line_items": 85, "excel_row": 85, 
            "text_section": 75, "text_naive": 50
        }
        base = base_map.get(c_type, 60)
        score += base
        reasons.append(f"Base({c_type})={base}")
        
        meta = chunk.get("strategy_meta") or chunk.get("metadata") or {}
        if meta.get("has_header"):
            score += 15
            reasons.append("HasHeader=15")
        
        text = chunk.get("text", "")
        keywords = ["합계", "Total", "VAT", "세액", "결론", "제1조", "Article", "목차", "조건"]
        if "total_amount:" in text.lower() or "invoice_id:" in text.lower():
            score += 20
            reasons.append("CanonicalField=20")
            
        found = [kw for kw in keywords if kw.lower() in text.lower()]
        if found:
            bonus = min(len(found) * 5, 20)
            score += bonus
            reasons.append(f"Keywords({len(found)})={bonus}")
            
        if len(text) < 50:
            score -= 30
            reasons.append("TooShort=-30")
        
        return score, reasons

    def rank_and_select_chunks(self, chunks: List[Dict[str, Any]], cap: int, doc_context: Dict[str, Any]) -> List[Dict[str, Any]]:
        for c in chunks:
            s, r = self.calculate_chunk_score(c, doc_context)
            c['score'] = s
            c['score_reasons'] = r
            
        sorted_chunks = sorted(chunks, key=lambda x: x.get('score', 0), reverse=True)
        
        if cap > 0 and self.enable_ranking:
            selected = sorted_chunks[:cap]
            logger.info(f"🏆 [Ranking] Cap={cap}, Before={len(chunks)}, After={len(selected)}")
            return selected
        
        return sorted_chunks

    def guess_page_range(self, start_offset: int, end_offset: int, pages: List[Dict[str, Any]]) -> tuple:
        current_pos = 0
        start_page = None
        end_page = None
        for p in pages:
            p_len = len(p.get("text", ""))
            p_start = current_pos
            p_end = current_pos + p_len
            current_pos += p_len
            if start_page is None and start_offset < p_end: 
                start_page = p.get("page_no", 1)
            
            if end_page is None and end_offset <= p_end: 
                end_page = p.get("page_no", 1)
                break
        if start_page is None and pages: start_page = pages[-1].get("page_no")
        if end_page is None and pages: end_page = pages[-1].get("page_no")
        return start_page, end_page

    def process_single_document(self, doc_id: str):
        # 1. Profile
        profile_ref = self.db.collection("profiles").document(doc_id).get()
        if not profile_ref.exists: return
        profile_data = profile_ref.to_dict()
        if not profile_data.get("active", True): return

        logger.info(f"✂️ [Chunk] 청킹 시작: {doc_id}")
        start_time = time.time()
        
        # 2. SSOT
        res_ref = self.db.collection("docai_results").document(doc_id).get()
        if not res_ref.exists: return
        docai_result = res_ref.to_dict()
        content_hash = profile_data.get("doc_content_hash", "nohash")
        full_text = docai_result.get("full_text", "")
        pages = docai_result.get("pages", [])
        
        # 3. Strategy
        strategy = self.get_chunking_strategy(profile_data, docai_result, settings)
        logger.info(f" -> Strategy: {strategy}")
        
        # 4. Generate Raw Chunks
        raw_struct_chunks = []
        doc_title = profile_data.get("title", "")
        
        if strategy == "excel":
            raw_struct_chunks = self.excel_chunking_logic(docai_result)
        elif strategy == "invoice_ocr":
            raw_struct_chunks = self.invoice_chunking_logic(docai_result)
        else:
            summary_chunk = self.generate_heuristic_summary(full_text, doc_title)
            raw_struct_chunks.append(summary_chunk)
            
            if self.use_section_chunking and full_text:
                body_chunks = self.section_aware_text_chunking(full_text, self.section_target_size, self.chunk_overlap)
            else:
                body_chunks = self.naive_text_chunking(full_text, self.chunk_size, self.chunk_overlap)
            raw_struct_chunks.extend(body_chunks)

        # 5. Standardization
        final_chunks = []
        doc_summary = profile_data.get("summary", "")
        
        for idx, item in enumerate(raw_struct_chunks):
            if 'start_char_idx' in item:
                p_start, p_end = self.guess_page_range(item['start_char_idx'], item['end_char_idx'], pages)
            else:
                p_start, p_end = 1, 1
            
            chunk_obj = {
                "chunk_id": f"{doc_id}:chunk:{idx}",
                "type": item.get('type', 'text'),
                "text": item['text'],
                "page_start_no": p_start,
                "page_end_no": p_end,
                "doc_title": doc_title,
                "summary": doc_summary,
                "strategy": strategy,
                "strategy_meta": item.get('metadata'),
                "tokens_estimate": len(item['text']) // 4
            }
            final_chunks.append(chunk_obj)
            
        # 6. Rank and Select
        before_count = len(final_chunks)
        selected_chunks = self.rank_and_select_chunks(final_chunks, self.per_doc_cap, {"strategy": strategy})
        after_count = len(selected_chunks)

        # 7. Save to GCS
        chunker_metadata = {
            "chunker_version": self.version,
            "strategy": strategy,
            "params": {"cap": self.per_doc_cap, "section_mode": self.use_section_chunking},
            "stats": {"before": before_count, "after": after_count},
            "created_at": time.time(),
            "doc_id": doc_id
        }
        output_payload = {"metadata": chunker_metadata, "chunks": selected_chunks}
        chunks_blob_path = f"chunks/{doc_id}/{content_hash}/chunks.json"
        
        try:
            self.bucket.blob(chunks_blob_path).upload_from_string(
                json.dumps(output_payload, ensure_ascii=False),
                content_type="application/json"
            )
        except Exception as e:
            logger.error(f"GCS Upload Fail: {e}")
        
        # 8. Firestore + Cache
        elapsed_ms = int((time.time() - start_time) * 1000)
        
        update_data = {
            "doc_id": doc_id,
            "chunk_count": after_count,
            "chunk_count_raw": before_count,
            "gcs_chunks_uri": f"gs://{self.bucket_name}/{chunks_blob_path}",
            "strategy": strategy,
            "chunker_version": self.version,
            "active": profile_data.get("active", True),
            "created_at": firestore.SERVER_TIMESTAMP,
            "elapsed_ms": elapsed_ms
        }
        
        if self.enable_top_chunk_cache:
            cache_limit = self.top_chunk_cache_max_chars
            cached_chunks = []
            
            for c in selected_chunks[:self.top_chunk_cache_k]:
                cached_chunk = {
                    "chunk_id": c["chunk_id"],
                    "type": c["type"],
                    "text": c["text"][:cache_limit] if c["text"] else "",
                    "page_start_no": c.get("page_start_no"),
                    "score": c.get("score")
                }
                cached_chunks.append(cached_chunk)
            
            update_data["top_chunk_cache"] = cached_chunks
            logger.info(f"   [Cache] {len(cached_chunks)} text chunks cached.")

        self.db.collection("chunks").document(doc_id).set(update_data, merge=True)
        
        self.db.collection("profiles").document(doc_id).set({
            "process_flags": {"chunk": False}
        }, merge=True)
        
        logger.info(f"✅ [Chunk] 생성 완료: {after_count} chunks (Raw: {before_count}) Strategy={strategy}")

if __name__ == "__main__":
    pass
