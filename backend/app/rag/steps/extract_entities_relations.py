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
            response = self.model.generate_content(prompt)
            raw_text = response.text.strip()
            if raw_text.startswith("```"):
                raw_text = raw_text.strip("`").replace("json\n", "").replace("json", "")
            return json.loads(raw_text)
        except Exception as e:
            logger.error(f"LLM Extract Fail: {e}")
            return {"entities": [], "relations": []}

    def load_chunks(self, chunks_uri: str):
        if not chunks_uri.startswith("gs://"): return []
        blob_path = chunks_uri.replace(f"gs://{self.bucket_name}/", "")
        blob = self.bucket.blob(blob_path)
        try:
            content = blob.download_as_text()
            return json.loads(content)
        except Exception:
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
        
        # 1. 길이 제한 (2글자 미만 제외, 단 영문 대문자 약어 등은 예외일 수 있으나 일단 엄격하게)
        # 한글 1글자("갑", "을", "법") 제외가 목적. 영문 "AI" 같은건 2글자라 통과.
        if len(name) < 2: return False
        
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
        (5) 표/리스트로 추정되는 청크 1개 (Optional)
        """
        text_chunks = [c for c in chunks if c.get("type", "text") == "text"]
        if not text_chunks: return []
        
        n = len(text_chunks)
        if n <= limit: return text_chunks

        selected_indices = set()
        
        # (1) Start
        selected_indices.add(0)
        
        # (2) Mid
        if n > 2:
            selected_indices.add(n // 2)
            
        # (3) End
        selected_indices.add(n - 1)
        
        # (4) Longest (남은 자리만큼)
        # 이미 선택된 것 제외하고 길이순 정렬
        remaining_indices = [i for i in range(n) if i not in selected_indices]
        sorted_by_len = sorted(remaining_indices, key=lambda i: len(text_chunks[i].get("text", "")), reverse=True)
        
        slots_left = limit - len(selected_indices)
        for i in range(min(slots_left, len(sorted_by_len))):
            selected_indices.add(sorted_by_len[i])
            
        # 인덱스 순으로 정렬하여 반환
        return [text_chunks[i] for i in sorted(list(selected_indices))]

    def process_single_document(self, doc_id: str):
        profile_ref = self.db.collection("profiles").document(doc_id).get()
        if not profile_ref.exists: return
        profile = profile_ref.to_dict()
        if not profile.get("active"): return

        logger.info(f"🕸️ [Entity] 추출 시작: {doc_id}")

        chunk_ref = self.db.collection("chunks").document(doc_id).get()
        if not chunk_ref.exists: return
        
        chunks = self.load_chunks(chunk_ref.get("gcs_chunks_uri"))
        if not chunks: return

        # Selection Strategy (Improved)
        target_chunks = self._select_representative_chunks(chunks, limit=5)
        
        if not target_chunks: return
        
        # [Parallel Extraction]
        import concurrent.futures
        
        final_entities = []
        all_relations = []
        source_link = profile.get("source_link")
        
        def _process_chunk(chunk):
            """Thread Worker Function"""
            text = chunk.get("text", "")
            if not text: return None
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
                        
                        # [NEW] 후처리 필터 적용
                        if not self._is_valid_entity(name):
                            continue
                            
                        norm_name = self._normalize_name(name)
                        ent["normalized_name"] = norm_name
                        ent["concept_key"] = f"{ent.get('type', 'UNKNOWN')}:{norm_name}"
                        ent["mention_count"] = 1 # 기본 1, 추후 merge시 합산 가능

                        ent["evidence"] = [{
                            "doc_id": doc_id,
                            "chunk_id": chunk_data.get("chunk_id"),
                            "page": chunk_data.get("page_start_no"),
                            "source_link": source_link,
                            "snippet": snippet, # [Fix] 실제 텍스트 사용
                            "span": None
                        }]
                        final_entities.append(ent)
                        
                    for rel in result.get("relations", []):
                        rel["evidence_chunk_id"] = chunk_data.get("chunk_id")
                        all_relations.append(rel)
                        
                except Exception as e:
                    logger.error(f"Chunk processing failed (chunk_id={chunk_data.get('chunk_id')}): {e}")

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
