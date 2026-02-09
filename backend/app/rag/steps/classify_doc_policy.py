import os
from dotenv import load_dotenv
load_dotenv()
import re
import json
import logging
from typing import Dict, Any, List, Tuple

from google.cloud import firestore

# [통합] Backend Imports
from app.core.config import settings
from app.core.gcp_clients import get_firestore_client
from app.common.enums import SecurityLevel, SSoTLevel

# Logger
logger = logging.getLogger("PolicyClassifier")
logger.setLevel(logging.INFO)

import datetime
from google.cloud import aiplatform
import vertexai
from vertexai.generative_models import GenerativeModel, GenerationConfig, SafetySetting, HarmCategory, HarmBlockThreshold

# --- SSOT Scorer ---
class SSoTScorer:
    """
    SSOT Reliability Scorer (0~100)
    Based on heuristics: Folder, Permissions, Title, Recency, Text Rules
    """
    def compute_score(self, profile: Dict[str, Any], text_sample: str = ""):
        signals = []
        base_score = 50 # Default Start

        folder_path = profile.get("folder_path", "/") or "/"
        title = profile.get("title", "") or ""
        perms = profile.get("permissions_summary", {})
        modified_time = profile.get("modified_time") # Timestamp or str

        # 1. Folder Rules (Max +25)
        if any(x in folder_path for x in ["표준서식", "전사_공유", "정책", "가이드", "매뉴얼", "Official", "Policy", "Manual"]):
            delta = 20
            base_score += delta
            signals.append({"source": "meta", "name": "folder_official", "delta": delta, "evidence": "Official Folder Path"})
        elif any(x in folder_path for x in ["시장_경제_동향", "리서치", "레퍼런스", "Reference", "Research"]):
            delta = 10
            base_score += delta
            signals.append({"source": "meta", "name": "folder_reference", "delta": delta, "evidence": "Reference Folder Path"})
        elif any(x in folder_path for x in ["개인", "임시", "참고", "Personal", "Temp"]):
            delta = 5
            base_score += delta # Small boost for just existing? Or maybe 0. Let's say +5 as base trust.
            signals.append({"source": "meta", "name": "folder_personal", "delta": delta, "evidence": "Personal/Temp Folder"})

        # 2. Permissions Rules (Penalty)
        if perms.get("anyone_can_read"):
            delta = -10
            base_score += delta
            signals.append({"source": "meta", "name": "anyone_can_read", "delta": delta, "evidence": "Public Read Access"})
        
        # 3. Title Rules
        lower_title = title.lower()
        if any(x in lower_title for x in ["최종", "final", "확정", "승인", "개정", "rev", "v2", "v3"]):
            delta = 10
            base_score += delta
            signals.append({"source": "meta", "name": "title_final", "delta": delta, "evidence": "Final/Revision Keyword in Title"})
        elif any(x in lower_title for x in ["초안", "draft", "임시", "참고", "검토", "copy"]):
            delta = -10
            base_score += delta
            signals.append({"source": "meta", "name": "title_draft", "delta": delta, "evidence": "Draft Keyword in Title"})

        # 4. Recency (If available)
        # Assuming modified_time is accessible. If not, skip.
        # Simple check: if within 90 days +5
        # (Skipped for simplicity or implementation complexity with datetime parsing)

        # 5. Text Patterns (Using text_sample)
        # Sample text check
        if text_sample:
            # Positive structural keywords
            if any(x in text_sample for x in ["목차", "결론", "부칙", "개정 이력", "Terms", "Index"]):
                delta = 10
                base_score += delta
                signals.append({"source": "text_rule", "name": "text_structure", "delta": delta, "evidence": "Structured Document content"})
            
            # Negative draft keywords in content
            if any(x in text_sample for x in ["대외비", "작성중", "CONFIDENTIAL DRAFT"]):
                delta = -10
                base_score += delta
                signals.append({"source": "text_rule", "name": "text_draft_mark", "delta": delta, "evidence": "Draft/Confidential markers in text"})

        # Clamp 0~100
        final_score = max(0, min(100, base_score))
        
        # [Fix] Add default signal if no rules matched
        if not signals:
            signals.append({
                "source": "default", 
                "name": "baseline", 
                "delta": 0, 
                "evidence": "표준 신뢰도 기준 적용 (특이사항 없음)"
            })
        
        return final_score, signals

# --- SSOT Explainer ---
class SSoTExplainer:
    def __init__(self, mode="rule_only"):
        self.mode = mode # 'rule_only' or 'llm_summary'
        self.max_output_tokens = int(os.getenv("SSOT_EXPLAIN_LLM_MAX_TOKENS", 512))
        
        # Init Vertex AI if needed
        if self.mode == "llm_summary":
            try:
                vertexai.init(project=settings.PROJECT_ID, location=settings.VERTEX_LOCATION)
                model_name = os.getenv("EXPLAINER_LLM_MODEL", "gemini-2.5-flash")
                self.model = GenerativeModel(model_name)
                logger.info(f"SSOT Explainer using model: {model_name}")
            except Exception as e:
                logger.warning(f"Vertex AI Init failed for SSOT Explainer: {e}. Fallback to rule_only.")
                self.mode = "rule_only"

    def generate_explanation(self, score: int, signals: List[Dict]) -> Tuple[str, List[str]]:
        """Returns (explanation_text, keywords)"""
        
        # Sort signals by absolute delta impact (descending)
        sorted_signals = sorted(signals, key=lambda x: abs(x['delta']), reverse=True)
        top_signals = sorted_signals[:3]
        
        # 1. Rule Only Builder
        rule_text_parts = []
        for s in top_signals:
            sign = "+" if s['delta'] > 0 else "-"
            rule_text_parts.append(f"{s['evidence']}({sign})")
        
        fallback_text = f"SSOT Score {score}: " + ", ".join(rule_text_parts) if rule_text_parts else f"SSOT Score {score} (Default)"
        fallback_keywords = [s['name'] for s in top_signals]

        # 2. LLM Summary
        if self.mode == "llm_summary":
            response_text = "N/A"
            try:
                prompt = f"""
You are a Document Reliability Analyst.

Task:
Given ssot_score and ssot_signals, write a ONE-LINE Korean explanation for a UI card.

Constraints:
- Use ONLY the provided signals. Do NOT invent any facts.
- Mention at most 2~3 strongest reasons (largest absolute delta).
- Output MUST be Korean only.
- Keep one_liner within 80 Korean characters.
- Do not include markdown code blocks. Just raw JSON.

Input:
ssot_score = {score}/100
ssot_signals (top) = {json.dumps(sorted_signals, ensure_ascii=False)}

Output JSON ONLY (no markdown, no extra text):
{{"one_liner":"...", "keywords":["...","...","..."]}}
- keywords: 2~3 short Korean keywords
"""
                response = self.model.generate_content(
                    prompt,
                    generation_config=GenerationConfig(
                        max_output_tokens=1024,
                        temperature=0.2
                    ),
                    safety_settings=[
                        SafetySetting(
                            category=HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT,
                            threshold=HarmBlockThreshold.BLOCK_ONLY_HIGH
                        ),
                        SafetySetting(
                            category=HarmCategory.HARM_CATEGORY_HATE_SPEECH,
                            threshold=HarmBlockThreshold.BLOCK_ONLY_HIGH
                        ),
                        SafetySetting(
                            category=HarmCategory.HARM_CATEGORY_HARASSMENT,
                            threshold=HarmBlockThreshold.BLOCK_ONLY_HIGH
                        ),
                        SafetySetting(
                            category=HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT,
                            threshold=HarmBlockThreshold.BLOCK_ONLY_HIGH
                        ),
                    ]
                )
                
                # Robust JSON extraction
                response_text = response.text.strip()
                
                # Debug Log
                logger.info(f"[SSoT LLM Raw]: {response_text}")

                # Try to extract JSON from response (handle markdown code blocks or plain text)
                json_match = re.search(r'\{.*\}', response_text, re.DOTALL)
                if json_match:
                    response_text = json_match.group(0)
                
                res_json = json.loads(response_text)
                return res_json.get("one_liner", fallback_text), res_json.get("keywords", fallback_keywords)

            except Exception as e:
                logger.error(f"LLM Explanation failed: {e}. Raw Response: {response_text}")
                return fallback_text, fallback_keywords

        return fallback_text, fallback_keywords

# --- Security Explainer (New) ---
class SecurityExplainer:
    def __init__(self, mode="rule_only"):
        self.mode = mode # 'rule_only' or 'llm_summary'
        self.max_output_tokens = int(os.getenv("SECURITY_EXPLAIN_LLM_MAX_TOKENS", 512))
        
        # Init Vertex AI if needed (Reusing existing init if possible, but safe to re-init)
        if self.mode == "llm_summary":
            try:
                vertexai.init(project=settings.PROJECT_ID, location=settings.VERTEX_LOCATION)
                model_name = os.getenv("EXPLAINER_LLM_MODEL", "gemini-2.5-flash")
                self.model = GenerativeModel(model_name)
                logger.info(f"Security Explainer using model: {model_name}")
            except Exception as e:
                logger.warning(f"Vertex AI Init failed for Security Explainer: {e}. Fallback to rule_only.")
                self.mode = "rule_only"

    def generate_explanation(self, security_level: str, signals: List[Dict]) -> Tuple[str, List[str], str]:
        """Returns (explanation_text, keywords, mode_used)"""
        
        # 1. Rule Only Builder (Fallback)
        # Sort signals just in case, though usually pre-sorted or order matters
        # Prioritize 'raise' > 'cap' > 'base' if needed, but simple list is fine
        top_signals = signals[:6]
        
        rule_text_parts = []
        for s in top_signals:
            rule_text_parts.append(f"{s['evidence']}")
        
        fallback_text = f"Security Level {security_level}: " + " + ".join(rule_text_parts) if rule_text_parts else f"Security Level {security_level} (Default)"
        fallback_keywords = [s['name'] for s in top_signals]

        # 2. LLM Summary
        if self.mode == "llm_summary":
            response_text = "N/A"
            try:
                prompt = f"""
You are a Corporate Security Analyst.

Task:
Given the security_level and a list of security_signals, write a ONE-LINE Korean explanation for a UI card.

Constraints:
- Use ONLY the provided signals. Do NOT invent any facts.
- Mention at most 2~3 strongest reasons (highest impact signals).
- If any signal name indicates a sensitive pattern (e.g., RRN, Salary, Account), explicitly name that pattern.
- If any signal indicates permission cap/restriction, mention it briefly.
- Output MUST be Korean only.
- Keep one_liner within 80 Korean characters.
- Do not include markdown code blocks. Just raw JSON.

Input:
security_level = {security_level}
security_signals (top) = {json.dumps(top_signals, ensure_ascii=False)}

Output JSON ONLY (no markdown, no extra text):
{{"one_liner":"...", "keywords":["...","..."], "risk_note":null}}
- keywords: 2~3 short Korean keywords
- risk_note: null unless there is a clear permission/exposure risk signal
"""
                response = self.model.generate_content(
                    prompt,
                    generation_config=GenerationConfig(
                        max_output_tokens=1024,
                        temperature=0.2
                    ),
                    safety_settings=[
                        SafetySetting(
                            category=HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT,
                            threshold=HarmBlockThreshold.BLOCK_ONLY_HIGH
                        ),
                        SafetySetting(
                            category=HarmCategory.HARM_CATEGORY_HATE_SPEECH,
                            threshold=HarmBlockThreshold.BLOCK_ONLY_HIGH
                        ),
                        SafetySetting(
                            category=HarmCategory.HARM_CATEGORY_HARASSMENT,
                            threshold=HarmBlockThreshold.BLOCK_ONLY_HIGH
                        ),
                        SafetySetting(
                            category=HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT,
                            threshold=HarmBlockThreshold.BLOCK_ONLY_HIGH
                        ),
                    ]
                )
                
                # Robust JSON extraction
                response_text = response.text.strip()
                
                # Debug Log
                logger.info(f"[Security LLM Raw]: {response_text}")

                # Try to extract JSON from response (handle markdown code blocks or plain text)
                json_match = re.search(r'\{.*\}', response_text, re.DOTALL)
                if json_match:
                    response_text = json_match.group(0)
                
                res_json = json.loads(response_text)
                return res_json.get("one_liner", fallback_text), res_json.get("keywords", fallback_keywords), "llm_summary"

            except Exception as e:
                logger.error(f"LLM Security Explanation failed: {e}. Raw Response: {response_text}")
                return fallback_text, fallback_keywords, "rule_only (fallback)"

        return fallback_text, fallback_keywords, "rule_only"

# --- Rule Engine (Legacy Wrapper) ---

# ... (SSoTScorer and SSoTExplainer classes remain unchanged) ...

# --- Rule Engine (Legacy Wrapper) ---
class PolicyEngine:
    # ... (Existing PolicyEngine code unchanged) ...
    def __init__(self, rules_path: str):
        if os.path.exists(rules_path):
            with open(rules_path, 'r', encoding='utf-8') as f:
                self.rules = json.load(f)
        else:
            self.rules = {}
            
    def evaluate(self, profile: Dict[str, Any]) -> Dict[str, Any]:
        # Legacy Logic for security_level / ssot_level (Gold/Silver)
        result = {
            "security_level": SecurityLevel.HIGH.value,
            "ssot_level": SSoTLevel.SILVER.value,
            "matched_rules": []
        }
        
        folder_path = profile.get("folder_path", "/") or "/"
        title = profile.get("title", "")
        perms = profile.get("permissions_summary", {})
        
        matched_results = [] 
        
        for rule in self.rules.get("folder_rules", []):
            if rule["pattern"] in folder_path:
                matched_results.append({"priority": 100, "security": rule["security"], "ssot": rule["ssot"], "reason": f"Folder Match: {rule['pattern']}"})
        
        for rule in self.rules.get("keyword_rules", []):
            if rule["keyword"] in title:
                matched_results.append({"priority": 50, "security": rule["security"], "ssot": rule["ssot"], "reason": f"Keyword Match: {rule['keyword']}"})
                
        if matched_results:
            matched_results.sort(key=lambda x: x["priority"], reverse=True)
            top_match = matched_results[0]
            result["security_level"] = SecurityLevel.normalize(top_match["security"]).value
            result["ssot_level"] = SSoTLevel.normalize(top_match["ssot"]).value
            if "ssot" in top_match: 
                 result["ssot_level"] = SSoTLevel.normalize(top_match["ssot"]).value
            for m in matched_results: result["matched_rules"].append(m["reason"])
        
        # Legacy Cap
        if perms.get("anyone_can_read") is True and result["security_level"] == SecurityLevel.HIGH.value:
            result["security_level"] = SecurityLevel.MEDIUM.value
            result["matched_rules"].append("Downgraded by Owner Permission")

        return result

# --- Main Processor ---
class PolicyClassifier:
    def __init__(self):
        self.db = get_firestore_client()
        self.tenant_id = getattr(settings, "TENANT_ID", "default_tenant")
        self.engagement_id = getattr(settings, "ENGAGEMENT_ID", "default_engagement")
        
        # V1 Engine Init
        self.policy_version = os.getenv("SECURITY_POLICY_VERSION", "v1") # Env Var toggle
        self.v1_rules_file = os.path.join("app", "rag", "rules", "policy_rules.v1.json")
        self.engine = PolicyEngine(self.v1_rules_file)
        
        # V2 Rules Load
        self.v2_rules = {}
        if self.policy_version == "v2":
            v2_path = os.path.join("app", "rag", "rules", "policy_rules.v2.security.json")
            if os.path.exists(v2_path):
                with open(v2_path, 'r', encoding='utf-8') as f:
                    self.v2_rules = json.load(f)
            else:
                logger.warning(f"V2 Rules file not found at {v2_path}, falling back to V1")
                self.policy_version = "v1"

        # New SSOT Modules
        self.scorer = SSoTScorer()
        self.explain_mode = os.getenv("SSOT_EXPLAIN_MODE", "rule_only")
        self.explainer = SSoTExplainer(mode=self.explain_mode)
        
        # New Security Explainer
        self.sec_explain_mode = os.getenv("SECURITY_EXPLAIN_MODE", "rule_only")
        self.sec_explainer = SecurityExplainer(mode=self.sec_explain_mode)

    def compute_security_decision_v2(self, profile: Dict[str, Any], text_sample: str = "") -> Tuple[str, List[Dict], str]:
        """
        V2 Security Logic: Base -> Raise -> Cap
        Returns: (security_level, signals, explain_seed)
        """
        signals = []
        folder_path = profile.get("folder_path", "/") or "/"
        title = profile.get("title", "") or ""
        perms = profile.get("permissions_summary", {})
        
        # Level Mapping: Low=1, Medium=2, High=3
        level_map = {"Low": 1, "Medium": 2, "High": 3}
        rev_map = {1: "Low", 2: "Medium", 3: "High"}
        current_level_val = 1 # Default Low
        
        # 1. Base Rules (Folder/Title)
        base_rules = self.v2_rules.get("security_base_rules", [])
        matched_base = False
        for rule in base_rules:
            pattern = rule.get("pattern", "")
            # Simple regex search for pattern in folder or title
            if re.search(pattern, folder_path, re.IGNORECASE) or re.search(pattern, title, re.IGNORECASE):
                lvl_str = rule.get("security", "Low")
                val = level_map.get(lvl_str, 1)
                if val > current_level_val:
                    current_level_val = val
                    signals.append({
                        "source": "v2_base", 
                        "name": "base_rule_match", 
                        "evidence": f"Base: {rule.get('description', pattern)}", 
                        "delta": 0
                    })
                    matched_base = True
        
        if not matched_base:
             signals.append({"source": "v2_base", "name": "default_low", "evidence": "Default Base (Low)", "delta": 0})

        # 2. Raise Rules (Text Pattern)
        if text_sample:
            raise_rules = self.v2_rules.get("security_raise_rules", [])
            for rule in raise_rules:
                pattern = rule.get("pattern", "")
                target_str = rule.get("security_target", "High")
                target_val = level_map.get(target_str, 3)
                
                if target_val > current_level_val:
                    if re.search(pattern, text_sample, re.IGNORECASE):
                        current_level_val = target_val
                        signals.append({
                            "source": "v2_raise",
                            "name": "sensitive_pattern",
                            "evidence": f"Sensitive: {rule.get('description', pattern)}",
                            "delta": 10
                        })
        
        # 3. Cap Rules (Permissions)
        cap_rules = self.v2_rules.get("security_cap_rules", [])
        for rule in cap_rules:
            cond = rule.get("condition")
            max_str = rule.get("security_max", "High")
            max_val = level_map.get(max_str, 3)
            
            check = False
            if cond == "anyone_can_read" and perms.get("anyone_can_read"):
                check = True
            elif cond == "external_share" and perms.get("external_shared"): # Assuming external_shared key exists
                check = True
                
            if check and current_level_val > max_val:
                current_level_val = max_val
                signals.append({
                    "source": "v2_cap",
                    "name": "permission_cap",
                    "evidence": f"Capped by: {rule.get('description', cond)}",
                    "delta": -10
                })

        final_level = rev_map.get(current_level_val, "Low")
        explain_seed = ", ".join([s['evidence'] for s in signals[:3]])
        
        return final_level, signals, explain_seed

    def process_single_document(self, doc_id: str):
        """Orchestrator 호출 포인트"""
        # 1. Profile 조회
        doc_ref = self.db.collection("profiles").document(doc_id).get()
        if not doc_ref.exists:
            logger.warning(f"SKIP Policy: Profile not found for {doc_id}")
            return
        doc_data = doc_ref.to_dict()
        if not doc_data.get("active"):
            logger.info(f"SKIP Policy: Document {doc_id} is not active")
            return

        logger.info(f"🛡️ [Policy] 분류 시작: {doc_id} (Ver: {self.policy_version})")
        
        # 2. Security Eval (V1 or V2)
        # Try fetch text sample first as V2 needs it for Raise rules
        text_sample = ""
        try:
            # [Fix] chunks collection uses doc_id as document key, not a field.
            # Text content is stored in GCS, need to load from there.
            chunks_meta = self.db.collection("chunks").document(doc_id).get()
            if chunks_meta.exists:
                gcs_uri = chunks_meta.get("gcs_chunks_uri")
                if gcs_uri:
                    from google.cloud import storage
                    bucket_name = getattr(settings, "GCS_BUCKET", f"{settings.PROJECT_ID}-docai-output")
                    storage_client = storage.Client(project=settings.PROJECT_ID)
                    blob_path = gcs_uri.replace(f"gs://{bucket_name}/", "")
                    bucket = storage_client.bucket(bucket_name)
                    blob = bucket.blob(blob_path)
                    chunks_data = json.loads(blob.download_as_text())
                    if isinstance(chunks_data, dict):
                        chunks_data = chunks_data.get("chunks", [])
                    # Get text from first few chunks for sampling
                    text_parts = []
                    for c in chunks_data[:3]:  # First 3 chunks
                        if str(c.get("type", "text")).startswith(("text", "doc", "excel", "invoice")):
                            text_parts.append(c.get("text", ""))
                    text_sample = " ".join(text_parts)[:3000]  # Increased for V2 pattern matching
        except Exception as e:
            logger.warning(f"Failed to fetch text sample: {e}")

        security_level = SecurityLevel.HIGH.value
        ssot_level = SSoTLevel.SILVER.value
        v2_signals = []
        
        if self.policy_version == "v2":
            try:
                security_level, v2_signals, _ = self.compute_security_decision_v2(doc_data, text_sample)
                # Note: SSOT Level logic is not overlapping with V2 Security, keeping V1 logic for SSOT/Tag for now or default
                # Just reusing V1 evaluate for SSOT part if needed, or default to Silver/Gold based on score?
                # For now, let's keep V1 evaluate for SSOT tag specifically, but overwrite security_level
                v1_result = self.engine.evaluate(doc_data)
                ssot_level = v1_result["ssot_level"]
                
                logger.info(f"V2 Decision: {security_level}")
            except Exception as e:
                logger.error(f"V2 Policy Failed: {e}, reverting to V1")
                v1_result = self.engine.evaluate(doc_data)
                security_level = v1_result["security_level"]
                ssot_level = v1_result["ssot_level"]
        else:
            # V1 Legacy
            eval_result = self.engine.evaluate(doc_data)
            security_level = eval_result["security_level"]
            ssot_level = eval_result["ssot_level"]
        
        # 3. SSOT Score (Scorer)
        ssot_score, ssot_signals = self.scorer.compute_score(doc_data, text_sample)
        ssot_explain, ssot_keywords = self.explainer.generate_explanation(ssot_score, ssot_signals)

        # Merge V2 signals into SSOT signals for visibility if V2 is active (Optional visuals)
        # Or just keep them separate. Let's keep separate in backend but maybe meaningful to log.
        
        # --- Generate Security Explanation (Rule Only or LLM) ---
        security_explain = ""
        security_keywords = []
        security_explanation_mode_used = "rule_only"
        
        if self.policy_version == "v2":
            security_explain, security_keywords, security_explanation_mode_used = self.sec_explainer.generate_explanation(security_level, v2_signals)
        else:
             # V1 Fallback (Use matched_rules from eval_result)
             if eval_result.get("matched_rules"):
                 security_explain = " + ".join(eval_result["matched_rules"][:2])
             else:
                 security_explain = f"Legacy Rule: {security_level}"


        # 4. 저장 데이터 구성
        policy_data = {
            "doc_id": doc_id,
            "tenant_id": self.tenant_id,
            "engagement_id": self.engagement_id,
            "doc_content_hash": doc_data.get("doc_content_hash"),
            "security_level": security_level,
            "ssot_level": ssot_level,
            "matched_rules": [s['evidence'] for s in v2_signals] if v2_signals else eval_result.get("matched_rules", []),
            
            # New Security Fields (Reason Card)
            "security_signals": v2_signals if self.policy_version == "v2" else [],
            "security_explain": security_explain,
            "security_keywords": security_keywords,
            "security_rules_version": "sec.v2.0" if self.policy_version == "v2" else "v1",
            "security_explain_mode": security_explanation_mode_used,

            # New SSOT Fields
            "ssot_score": ssot_score,
            "ssot_signals": ssot_signals,
            "ssot_explain": ssot_explain,
            "ssot_keywords": ssot_keywords,
            
            "rule_version": self.policy_version,
            "classified_at": firestore.SERVER_TIMESTAMP
        }
        
        batch = self.db.batch()
        
        # policies/{doc_id}
        batch.set(self.db.collection("policies").document(doc_id), policy_data, merge=True)
        
        # documents/{doc_id} (Serving Cache)
        batch.set(self.db.collection("documents").document(doc_id), {
            "security_level": security_level,
            "ssot_level": ssot_level,
            # New Fields Cache
            "ssot_score": ssot_score,
            "ssot_explain": ssot_explain,
            "security_explain": security_explain # Added
        }, merge=True)
        
        # profiles/{doc_id} (Flag Off)
        batch.set(self.db.collection("profiles").document(doc_id), {
            "process_flags": {"policy": False}
        }, merge=True)

        batch.commit()
        logger.info(f"✅ [Policy] 분류 완료(v{self.policy_version}): {security_level} / SSOT: {ssot_score} / Reason: {security_explain}")
