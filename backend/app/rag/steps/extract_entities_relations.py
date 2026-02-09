import json
import logging
import time
import os
import re
import vertexai
from vertexai.generative_models import GenerativeModel
from google.cloud import storage
from google.cloud import firestore

# [통합] Backend Imports
from app.core.config import settings
from app.core.gcp_clients import get_firestore_client

# Logger
logger = logging.getLogger("EntityExtractor")
logger.setLevel(logging.INFO)

class EntityExtractor:
    def __init__(self):
        self.db = get_firestore_client()
        self.project_id = settings.PROJECT_ID
        self.location = getattr(settings, "VERTEX_LOCATION", "us-central1")
        self.bucket_name = getattr(settings, "GCS_BUCKET", f"{self.project_id}-docai-output")
        self.bucket = storage.Client(project=self.project_id).bucket(self.bucket_name)

        # Vertex Init
        vertexai.init(project=self.project_id, location=self.location)
        model_name = getattr(settings, "VERTEX_MODEL_NAME", "gemini-2.0-flash-exp")
        self.model = GenerativeModel(model_name)
        
        # Config (Types)
        # Load rules from text file
        self.types = ["PERSON", "ORGANIZATION", "LOCATION", "EVENT", "CONCEPT", "PRODUCT", "TECHNOLOGY"]
        types_file = os.path.join("app", "rag", "rules", "entity_types.txt")
        
        if os.path.exists(types_file):
            try:
                with open(types_file, "r", encoding="utf-8") as f:
                    # 빈 줄 제외하고 대문자로 변환하여 리스트 생성
                    self.types = [line.strip() for line in f if line.strip()]
                logger.info(f"Loaded {len(self.types)} entity types from {types_file}")
            except Exception as e:
                logger.warning(f"Failed to load entity types: {e}")
        else:
            logger.warning(f"Entity types file not found at {types_file}. Using defaults.")
        self.types_str = ", ".join(self.types)

        # Load Stopwords
        self.stopwords = set()
        stopwords_file = os.path.join("app", "rag", "rules", "stopwords.txt")
        if os.path.exists(stopwords_file):
            try:
                with open(stopwords_file, "r", encoding="utf-8") as f:
                    self.stopwords = {line.strip() for line in f if line.strip()}
                logger.info(f"Loaded {len(self.stopwords)} stopwords from {stopwords_file}")
            except Exception as e:
                logger.warning(f"Failed to load stopwords: {e}")

    def extract(self, text: str):
        prompt = f"""
        You are an advanced Information Extraction system.
        Extract meaningful Entities and Relations from the following text based on the allowed types.
        
        Allowed Entity Types: {self.types_str}
        
        [EXCLUSION RULES - STRICTLY ENFORCE]
        1. **Common Dates**: Do NOT extract simple dates like "2024년", "1월", "오늘", "내일". (Only extract specific historical events).
        2. **Legal Jargon**: Do NOT extract generic legal terms like "갑", "을", "병", "제1조", "본 계약", "당사자", "상기", "이하".
        3. **Pronouns**: Do NOT extract pronouns like "그", "이것", "저것", "본인".
        4. **Generic Terms**: Do NOT extract very common words that are not specific entities (e.g., "사람", "내용", "사항").
        
        Format Requirements:
        - Output Must be valid JSON.
        - JSON Structure:
          {{
            "entities": [ {{"name": "...", "type": "...", "aliases": ["..."]}} ],
            "relations": [ {{"src": "...", "rel_type": "...", "dst": "..."}} ]
          }}
        - Limit to key entities (exclude trivial ones).
        - Keep names normalized (e.g. 'Apple Inc.' instead of 'Apple').
        
        Input Text:
        {text[:20000]}
        
        Output JSON:
        """
        try:
            from vertexai.generative_models import HarmCategory, HarmBlockThreshold
            
            safety = {
                HarmCategory.HARM_CATEGORY_HATE_SPEECH: HarmBlockThreshold.BLOCK_NONE,
                HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: HarmBlockThreshold.BLOCK_NONE,
                HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: HarmBlockThreshold.BLOCK_NONE,
                HarmCategory.HARM_CATEGORY_HARASSMENT: HarmBlockThreshold.BLOCK_NONE,
            }
            
            # Use JSON Mode if supported
            config = {"response_mime_type": "application/json"}
            
            response = self.model.generate_content(prompt, safety_settings=safety, generation_config=config)
            
            raw_text = response.text.strip()
            if raw_text.startswith("```"):
                raw_text = raw_text.strip("`").replace("json\n", "").replace("json", "")
            return json.loads(raw_text)
            
        except ValueError as ve:
            # Content blocked or empty
            logger.warning(f"LLM Extract Blocked/Empty: {ve}")
            return {"entities": [], "relations": []}
        except Exception as e:
            logger.error(f"LLM Extract Fail: {e}")
            return {"entities": [], "relations": []}

    def load_chunks(self, chunks_uri: str):
        if not chunks_uri.startswith("gs://"): return []
        blob_path = chunks_uri.replace(f"gs://{self.bucket_name}/", "")
        blob = self.bucket.blob(blob_path)
        try:
            content = blob.download_as_text()
            data = json.loads(content)
            if isinstance(data, dict):
                return data.get("chunks", [])
            return data
        except Exception as e:
            logger.warning(f"Failed to load chunks from {chunks_uri}: {e}")
            return []

    def _normalize_name(self, name: str) -> str:
        """
        정규화: 소문자, 양옆 공백 제거, 구두점 제거 등 (build_concepts와 일관성 유지)
        """
        if not name: return ""
        # 소문자 변환 및 양옆 공백 제거
        norm = name.lower().strip()
        # 구두점 제거 (알파벳, 숫자, 공백, 한글 등은 유지하고 특수문자 제거)
        # 여기서는 단순하게 build_concepts의 로직을 따르되 좀 더 안전하게 처리
        norm = re.sub(r'[^\w\s]', '', norm) 
        # 연속된 공백을 하나로
        norm = re.sub(r'\s+', ' ', norm)
        return norm.strip()

    def _is_valid_entity(self, name: str) -> bool:
        """후처리 필터: 불용어, 날짜 패턴, 길이 제한 등"""
        if not name: return False
        name = name.strip()
        
        # 1. 길이 제한 완화 (1글자 이상이면 통과시키되, 숫자/특수문자 단독인 경우 제외)
        if len(name) < 1: return False
        
        # 1글자인 경우: 한글이나 알파벳인지 확인
        if len(name) == 1:
            if not re.match(r'[a-zA-Z가-힣]', name):
                return False
        
        # 2. Stopwords
        if name in self.stopwords: return False
        
        # 3. 정규식 필터
        # 숫자만 있는 경우 ("123", "2024")
        if re.match(r'^\d+$', name): return False
        # 연도/월/일 패턴 ("2024년", "1월", "30일")
        if re.match(r'^\d{2,4}년$', name): return False
        if re.match(r'^\d{1,2}월$', name): return False
        if re.match(r'^\d{1,2}일$', name): return False
        # 제N조 패턴
        if re.match(r'^제\d+조$', name): return False
        
        return True

    def _select_representative_chunks(self, chunks: list, limit: int = 5) -> list:
        """
        LLM 비용 효율성을 고려한 전략적 청크 선택
        (1) 문서 앞 1개
        (2) 문서 중간 1개
        (3) 문서 끝 1개
        (4) 길이가 긴 청크 1~2개
        
        [Fix] 모든 타입의 청크를 허용합니다 (invoice_kv, table 등 포함)
        """
        # 1. 유효한 딕셔너리 형태의 청크만 필터링
        valid_chunks = [c for c in chunks if isinstance(c, dict)]
        
        if not valid_chunks:
             logger.warning(f"⚠️ No valid chunk objects found.")
             return []
        
        n = len(valid_chunks)
        # 전체 개수가 limit보다 적으면 전부 반환
        if n <= limit: return valid_chunks

        selected_indices = set()
        
        # (1) Start
        selected_indices.add(0)
        
        # (2) Mid
        if n > 2:
            selected_indices.add(n // 2)
            
        # (3) End
        selected_indices.add(n - 1)
        
        # (4) Heavy Content Selection
        # 텍스트가 있으면 텍스트 길이, 없으면(구조화 데이터) 문자열 변환 길이 추정
        def get_content_len(c):
            t = c.get("text", "")
            if t: return len(t)
            # 텍스트가 없으면 JSON 덤프 길이로 추정 (정보량 측정)
            return len(str(c))

        remaining_indices = [i for i in range(n) if i not in selected_indices]
        sorted_by_len = sorted(remaining_indices, key=lambda i: get_content_len(valid_chunks[i]), reverse=True)
        
        slots_left = limit - len(selected_indices)
        for i in range(min(slots_left, len(sorted_by_len))):
            selected_indices.add(sorted_by_len[i])
            
        # Fallback: 만약 선택된 것이 하나도 없다면 (로직상 희박하지만) 0번 강제 추가
        if not selected_indices:
            selected_indices.add(0)

        # 인덱스 순으로 정렬하여 반환
        return [valid_chunks[i] for i in sorted(list(selected_indices))]

    def process_single_document(self, doc_id: str):
        profile_ref = self.db.collection("profiles").document(doc_id).get()
        if not profile_ref.exists: return
        profile = profile_ref.to_dict()
        if not profile.get("active"): return

        logger.info(f"🕸️ [Entity] 추출 시작: {doc_id}")

        chunk_ref = self.db.collection("chunks").document(doc_id).get()
        if not chunk_ref.exists: return
        
        chunks = self.load_chunks(chunk_ref.get("gcs_chunks_uri"))
        if not chunks:
             logger.warning(f"⚠️ [Entity] Docs loaded but chunks empty: {doc_id}")
             return

        # Selection Strategy (Fixed: Accept All Types)
        target_chunks = self._select_representative_chunks(chunks, limit=5)
        
        if not target_chunks:
            # Fallback: Should not happen due to fallback in select method, but double check
            if chunks:
                target_chunks = [chunks[0]]
                logger.warning(f"⚠️ [Entity] Selection logic returned 0, forcing first chunk.")
            else:
                logger.warning(f"⚠️ [Entity] No target chunks selected for {doc_id}. Skipping.")
                return
        
        # [Parallel Extraction]
        import concurrent.futures
        
        final_entities = []
        all_relations = []
        source_link = profile.get("source_link")
        
        def _process_chunk(chunk):
            """Thread Worker Function: Handles Text Generation & Extraction"""
            text = chunk.get("text", "")
            
            # [Fix] 텍스트가 없는 구조화된 청크(invoice_kv, items 등)를 문자열로 변환
            if not text:
                parts = []
                # Invoice Fields
                if "invoice_kv" in chunk and isinstance(chunk["invoice_kv"], dict):
                    parts.append("[Invoice Fields]")
                    for k, v in chunk["invoice_kv"].items():
                        parts.append(f"{k}: {v}")
                # Line Items
                if "items" in chunk and isinstance(chunk["items"], list):
                    parts.append("\n[Line Items]")
                    for item in chunk["items"]:
                        if isinstance(item, dict):
                            item_str = ", ".join([f"{k}:{v}" for k,v in item.items()])
                            parts.append(f"- {item_str}")
                        else:
                            parts.append(f"- {item}")
                # Table Rows
                if "type" in chunk and "row" in str(chunk["type"]): # excel_row etc
                     # If text is present it would be handled above, but if strictly just fields
                     pass
                
                # 강제로 문자열화 시도 (JSON Dump)
                if not parts and chunk:
                     # e.g. unknown structured chunk
                     try:
                         text = json.dumps(chunk, ensure_ascii=False)
                     except:
                         text = str(chunk)
                else:
                    text = "\n".join(parts)

            if not text or len(text.strip()) < 5: 
                return None

            # Chunk 단위 추출
            return self.extract(text)

        # ThreadPoolExecutor를 사용해 병렬 LLM 호출 (IO Bound)
        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
            # Future와 Chunk 매핑
            future_to_chunk = {executor.submit(_process_chunk, c): c for c in target_chunks}
            
            for future in concurrent.futures.as_completed(future_to_chunk):
                chunk_data = future_to_chunk[future]
                try:
                    result = future.result()
                    if not result: continue
                    
                    # A. Snippet 생성 (실제 텍스트 기반)
                    chunk_text = chunk_data.get("text", "")
                    if not chunk_text:
                        # 텍스트가 없어서 생성한 경우, 해당 내용을 Snippet으로 사용
                        chunk_text = "Structured Data extracted as text."
                    
                    # 앞부분 300자 정도, 줄바꿈 정리
                    snippet_raw = chunk_text[:300].replace("\n", " ")
                    snippet = f"{snippet_raw}..." if len(chunk_text) > 300 else snippet_raw
                    
                    # 결과 병합 및 증거(Evidence) 매핑
                    for ent in result.get("entities", []):
                        # [Defense] LLM이 문자열 리스트로 반환하는 경우 처리
                        if isinstance(ent, str):
                            ent = {"name": ent, "type": "OTHERS", "aliases": []}
                        
                        if not isinstance(ent, dict): continue

                        # B. 정규화 키 추가
                        name = ent.get("name", "")
                        
                        # [NEW] 후처리 필터 적용 (완화됨)
                        if not self._is_valid_entity(name):
                            continue
                            
                        norm_name = self._normalize_name(name)
                        ent["normalized_name"] = norm_name
                        # concept_key should be unique identifier
                        ent["concept_key"] = f"{ent.get('type', 'UNKNOWN')}:{norm_name}"
                        ent["mention_count"] = 1 # 기본 1
                        
                        ent["evidence"] = [{
                            "doc_id": doc_id,
                            "chunk_id": chunk_data.get("chunk_id"),
                            "page": chunk_data.get("page_start_no"),
                            "source_link": source_link,
                            "snippet": snippet, 
                            "span": None
                        }]
                        final_entities.append(ent)
                        
                    for rel in result.get("relations", []):
                        rel["evidence_chunk_id"] = chunk_data.get("chunk_id")
                        all_relations.append(rel)
                        
                except Exception as e:
                    logger.error(f"Chunk processing failed (chunk_id={chunk_data.get('chunk_id')}): {e}", exc_info=True)

        logger.info(f"⚡ [Entity] 병렬 추출 완료: {len(target_chunks)} chunks -> {len(final_entities)} entities")

        # Save to GCS
        content_hash = profile.get("doc_content_hash", "nohash")
        gcs_path = f"entities/{doc_id}/{content_hash}/entities.json"
        blob = self.bucket.blob(gcs_path)
        payload = {
            "doc_id": doc_id,
            "entities": final_entities,
            "relations": all_relations,
            "created_at": time.time()
        }
        blob.upload_from_string(json.dumps(payload, ensure_ascii=False), content_type="application/json")
        gcs_uri = f"gs://{self.bucket_name}/{gcs_path}"
        
        # Firestore Update
        self.db.collection("entities").document(doc_id).set({
            "doc_id": doc_id,
            "gcs_entities_uri": gcs_uri,
            "entity_count": len(final_entities),
            "relation_count": len(all_relations),
            "updated_at": firestore.SERVER_TIMESTAMP
        }, merge=True)
        
        self.db.collection("documents").document(doc_id).set({
            "entity_count": len(final_entities)
        }, merge=True)
        
        self.db.collection("profiles").document(doc_id).set({
            "process_flags": {"entities": False}
        }, merge=True)
        
        logger.info(f"✅ [Entity] 추출 완료: {len(final_entities)} entities")
