import logging
import datetime
from google.cloud import firestore

# [통합] Backend Imports
from app.core.config import settings
from app.core.gcp_clients import get_firestore_client
from app.common.enums import SecurityLevel, SSoTLevel, ReviewStatus
from app.rag.doc_workflow_rules import DocWorkflowRules

# Logger
logger = logging.getLogger("DocIndexUpserter")
logger.setLevel(logging.INFO)

class DocIndexUpserter:
    def __init__(self):
        self.db = get_firestore_client()
        self.doc_index_version = getattr(settings, "DOC_INDEX_VERSION", "v1")

    def get_dict(self, collection: str, doc_id: str):
        ref = self.db.collection(collection).document(doc_id).get()
        return ref.to_dict() if ref.exists else {}

    def process_single_document(self, doc_id: str):
        profile_ref = self.db.collection("profiles").document(doc_id).get()
        if not profile_ref.exists: return
        profile_data = profile_ref.to_dict()
        if not profile_data.get("active"): return

        logger.info(f"🏁 [Meta] 메타 인덱싱 시작: {doc_id}")

        # Fetch dependency data
        card_doc_data = self.get_dict("cards", doc_id)
        policy_data = self.get_dict("policies", doc_id)
        current_doc = self.get_dict("documents", doc_id) # Current Index State

        # 1. Determine Review Status
        # If content changed (hash mismatch), reset to PENDING. 
        # Otherwise keep existing status.
        current_hash = current_doc.get("doc_content_hash")
        new_hash = profile_data.get("doc_content_hash")
        
        # If new doc, defaults to PENDING
        current_status = current_doc.get("review_status", ReviewStatus.PENDING.value)
        new_status = current_status
        
        if current_hash != new_hash:
            new_status = ReviewStatus.PENDING.value
            logger.info(f"Content Changed: Resetting status to PENDING for {doc_id}")

        # 2. Apply Workflow Rules (Centralized Logic)
        # This returns {active, graph_visible, searchable, review_status}
        workflow_flags = DocWorkflowRules.apply(new_status)
        
        # 3. Prepare Final Document Payload
        card_summary = card_doc_data.get("card", {})
        
        # Top Concepts: Keep existing if available (Ranker output)
        top_concepts = current_doc.get("top_concepts", [])
        
        final_doc = {
            "doc_id": doc_id,
            "tenant_id": getattr(settings, "TENANT_ID", "default"),
            "engagement_id": getattr(settings, "ENGAGEMENT_ID", "default"),
            
            # Metadata from Profile
            "title": profile_data.get("title", "Untitled"),
            "folder_path": profile_data.get("folder_path", "/"),
            "doctype": profile_data.get("doctype_hint", "unknown"),
            "modified_time": profile_data.get("modified_time"),
            "source_link": profile_data.get("source_link"),
            "doc_content_hash": new_hash,
            "drive_file_id": profile_data.get("drive_file_id"),
            
            # Extracted/Generated Data
            "card_summary": {
                "l1": card_summary.get("l1", "No Title"),
                "l2": card_summary.get("l2", ""),
                "l3": card_summary.get("l3", "")
            },
            "top_concepts": top_concepts,
            
            # Policies
            "security_level": SecurityLevel.normalize(policy_data.get("security_level")).value,
            "ssot_level": SSoTLevel.normalize(policy_data.get("ssot_level")).value,
            "matched_rules": policy_data.get("matched_rules", []),
            
            # Workflow Flags (Merged)
            **workflow_flags, # active, graph_visible, searchable, review_status
            
            # System Internal
            "index_version": self.doc_index_version,
            "updated_at": firestore.SERVER_TIMESTAMP
        }
        
        # 4. Upsert to documents
        self.db.collection("documents").document(doc_id).set(final_doc, merge=True)
        
        # 5. Clear Flag
        self.db.collection("profiles").document(doc_id).set({
            "process_flags": {"index_meta": False}
        }, merge=True)
        
        logger.info(f"✅ [Meta] 인덱싱 완료: Status={new_status}, Visible={workflow_flags.get('graph_visible')}")
