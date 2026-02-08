import os
import re
import logging
from typing import List, Dict, Any, Optional
import vertexai
from vertexai.generative_models import GenerativeModel, SafetySetting

logger = logging.getLogger("Generator")

# --- Env Config ---
PROJECT_ID = os.getenv("GCP_PROJECT_ID")
LOCATION = os.getenv("VERTEX_LOCATION", "us-central1")
MODEL_NAME = os.getenv("VERTEX_MODEL_NAME", "gemini-2.0-flash-exp")
MAX_CONTEXT = int(os.getenv("MAX_CONTEXT_CHUNKS", 10))
STRICT_FORMAT = os.getenv("STRICT_FORMAT", "false").lower() == "true"

# 컨텍스트 청크당 최대 글자수 (너무 긴 snippet 방지)
MAX_CHUNK_LENGTH = int(os.getenv("MAX_CHUNK_LENGTH", 1200))


class Generator:
    def __init__(self):
        # Initialize Vertex AI
        vertexai.init(project=PROJECT_ID, location=LOCATION)
        self.model = GenerativeModel(MODEL_NAME)
        
        # Safety Settings (운영 최소: 일부 필터 완화 가능하나 기본 유지)
        self.safety_settings = [
            SafetySetting(
                category=SafetySetting.HarmCategory.HARM_CATEGORY_HATE_SPEECH,
                threshold=SafetySetting.HarmBlockThreshold.BLOCK_ONLY_HIGH
            ),
            SafetySetting(
                category=SafetySetting.HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT,
                threshold=SafetySetting.HarmBlockThreshold.BLOCK_ONLY_HIGH
            ),
             SafetySetting(
                category=SafetySetting.HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT,
                threshold=SafetySetting.HarmBlockThreshold.BLOCK_ONLY_HIGH
            ),
             SafetySetting(
                category=SafetySetting.HarmCategory.HARM_CATEGORY_HARASSMENT,
                threshold=SafetySetting.HarmBlockThreshold.BLOCK_ONLY_HIGH
            ),
        ]

    def _format_context(self, chunks: List[Dict]) -> str:
        """
        검색된 청크들을 프롬프트에 주입할 컨텍스트 문자열로 변환
        
        개선사항:
        - 각 소스 사이에 구분선 (---) 추가
        - 메타 정보 강화 (Title / Page / doc_id)
        - 긴 텍스트 상한 처리 (truncated 표시)
        """
        context_parts = []
        for idx, chunk in enumerate(chunks[:MAX_CONTEXT]):
            # chunk key validation
            doc_title = chunk.get("doc_title") or chunk.get("title") or "Untitled"
            page = chunk.get("page", "?")
            doc_id = chunk.get("doc_id", "")
            
            # [Fix] Support both 'text' (legacy) and 'snippet' (Evidence schema)
            text = chunk.get("text") or chunk.get("snippet") or ""
            text = text.strip()
            
            # 긴 텍스트 truncate
            if len(text) > MAX_CHUNK_LENGTH:
                text = text[:MAX_CHUNK_LENGTH] + "... (truncated)"
            
            # 메타 라인 구성
            meta_line = f"[{idx+1}] 📄 **{doc_title}** | Page: {page}"
            if doc_id:
                meta_line += f" | ID: {doc_id[:8]}..."
            
            part = f"{meta_line}\n{text}"
            context_parts.append(part)
        
        # 구분선으로 소스 분리
        return "\n\n---\n\n".join(context_parts)

    def _postprocess_markdown(self, answer: str) -> str:
        """
        모델 출력 후처리: 개행/공백만 조정 (팩트 변경 금지)
        
        규칙:
        - ## 헤딩 앞에는 빈 줄 1줄 확보
        - 불릿 리스트 사이 과도한 공백 정리
        - 4줄 이상 이어지는 문단 덩어리는 문장 단위로 분리
        """
        if not answer:
            return answer
        
        lines = answer.split("\n")
        result_lines = []
        prev_empty = False
        
        for i, line in enumerate(lines):
            stripped = line.strip()
            
            # 1. 헤딩 앞에 빈 줄 확보
            if stripped.startswith("##") and result_lines and result_lines[-1].strip():
                result_lines.append("")
            
            # 2. 과도한 연속 빈 줄 제거 (최대 1줄)
            if not stripped:
                if prev_empty:
                    continue  # 연속 빈 줄 스킵
                prev_empty = True
            else:
                prev_empty = False
            
            result_lines.append(line)
        
        processed = "\n".join(result_lines)
        
        # 3. 긴 문단 쪼개기 (4문장 이상 연속)
        # 문장 끝 마침표/물음표/느낌표 뒤에 공백이 있으면 줄바꿈 삽입
        def split_long_paragraphs(text: str) -> str:
            # 이미 줄바꿈이 있는 구간은 건드리지 않음
            paragraphs = text.split("\n\n")
            new_paragraphs = []
            
            for para in paragraphs:
                # 불릿 리스트나 헤딩은 건드리지 않음
                if para.strip().startswith(("-", "*", "#", "[")):
                    new_paragraphs.append(para)
                    continue
                
                # 줄바꿈 없이 긴 문단인지 체크
                if "\n" not in para and len(para) > 200:
                    # 문장 단위로 쪼개기 (한국어/영어 문장 끝 패턴)
                    sentences = re.split(r'(?<=[.!?다요함음])\s+', para)
                    if len(sentences) >= 4:
                        # 2~3문장씩 묶어서 줄바꿈
                        chunks = []
                        for j in range(0, len(sentences), 2):
                            chunk = " ".join(sentences[j:j+2])
                            chunks.append(chunk)
                        para = "\n\n".join(chunks)
                
                new_paragraphs.append(para)
            
            return "\n\n".join(new_paragraphs)
        
        processed = split_long_paragraphs(processed)
        
        # 4. References 섹션 검증 (없으면 경고 로그)
        if "## 4)" not in processed and "References" not in processed:
            logger.warning("Format Warning: References 섹션이 없습니다. 모델 출력 형식 점검 필요.")
        
        return processed.strip()

    def _check_format_compliance(self, answer: str) -> bool:
        """응답이 필수 섹션을 포함하는지 검증"""
        required_patterns = [
            r"##\s*1\)",  # 요약 결론
            r"##\s*2\)",  # 상세 판단 근거
        ]
        for pattern in required_patterns:
            if not re.search(pattern, answer):
                return False
        return True

    def generate(self, query: str, chunks: List[Dict]) -> str:
        if not chunks:
            return "검색 결과가 없어 답변을 생성할 수 없습니다."
            
        context_str = self._format_context(chunks)
        
        # ============================================================
        # System Prompt (가독성 규칙 강화)
        # ============================================================
        system_instruction = """
당신은 회계/법률 분야의 전문 AI 어시스턴트 'Omnihub AI'입니다.
사용자의 질문에 대해 제공된 [Context]만을 바탕으로 답변해야 합니다.
없는 사실을 지어내지 마십시오. 정보가 부족하면 솔직히 말하세요.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📌 답변 형식 (필수 준수)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

## 1) 요약 결론
- 질문에 대한 핵심 답변을 두괄식으로 1~3문장 요약.
- 확정적 표현 자제 ("~로 판단됩니다", "~로 보입니다" 권장).

## 2) 상세 판단 근거
- Context의 내용을 바탕으로 논리적으로 설명.
- 반드시 불릿 포인트(- )를 사용하여 항목별 정리.
- 각 항목은 1~2문장으로 제한.

## 3) 리스크/확인 필요 사항
- 정보의 한계, 추가 확인 필요한 사항 언급.
- 해당 없으면 "특별한 리스크 없음"으로 간단히 마무리.

## 4) References
- 본문에서 실제로 인용한 [번호]만 나열.
- 사용하지 않은 번호는 절대 포함하지 마세요.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📌 가독성 규칙 (필수 준수)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

1. **문단 길이 제한**: 한 문단은 1~3문장. 문단 끝에는 반드시 빈 줄 1줄.
2. **줄바꿈 빈도**: 긴 문장은 두 문장으로 쪼갠다. 장문 금지.
3. **리스트 활용**: 3개 이상 항목 나열 시 반드시 불릿 리스트 사용.
4. **불릿 1줄 제한**: 불릿 한 줄은 1문장(최대 2문장).
5. **출처 표시**: 모든 주장 문장 끝에 [n] 출처 번호 필수.
   - 예: "...라고 규정되어 있습니다[1]."
   - 출처 불명확 시: "제공된 Context만으로는 확인 불가"라고 명시.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📌 톤앤매너
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

- 한국어로 답변.
- 건조하고 전문적인 톤 유지.
- 불필요한 수식어, 감정 표현 금지.
"""
        
        full_prompt = f"""
{system_instruction}

[Context]
{context_str}

[Question]
{query}

[Answer]
"""
        try:
            response = self.model.generate_content(
                full_prompt,
                safety_settings=self.safety_settings,
                generation_config={
                    "max_output_tokens": 2048,
                    "temperature": 0.2,  # 낮은 온도 (사실 기반)
                    "top_p": 0.8
                }
            )
            answer = response.text
            
            # 후처리 적용
            answer = self._postprocess_markdown(answer)
            
            # 형식 검증 (STRICT_FORMAT 모드일 때만 재시도)
            if STRICT_FORMAT and not self._check_format_compliance(answer):
                logger.warning("Format 불일치 감지. 형식 보정 재시도 중...")
                
                retry_prompt = f"""
{full_prompt}

[주의] 반드시 아래 형식으로 답변하세요:
## 1) 요약 결론
## 2) 상세 판단 근거  
## 3) 리스크/확인 필요 사항
## 4) References
"""
                retry_response = self.model.generate_content(
                    retry_prompt,
                    safety_settings=self.safety_settings,
                    generation_config={
                        "max_output_tokens": 2048,
                        "temperature": 0.2,
                        "top_p": 0.8
                    }
                )
                answer = self._postprocess_markdown(retry_response.text)
            
            return answer
            
        except Exception as e:
            logger.error(f"Generation Failed: {e}")
            return "죄송합니다. 답변 생성 중 오류가 발생했습니다."
