import os
import hashlib
import logging
from typing import Dict, Any, List, Set, Tuple
from datetime import datetime
from google.cloud import firestore
from app.core.config import settings
from app.core.gcp_clients import get_firestore_client
from app.common.enums import SecurityLevel, ReviewStatus

logger = logging.getLogger("TreeIndexerService")
logger.setLevel(logging.INFO)

class TreeIndexerService:
    def __init__(self):
        self.db = get_firestore_client()
        self.tree_cache = {}
        
        # Config
        self.folder_doc_cap = int(getattr(settings, "TREE_FOLDER_DOC_CAP", 500))
        self.docs_per_folder_cap = int(getattr(settings, "TREE_DOCS_PER_FOLDER_CAP", 300))
        self.version = getattr(settings, "TREE_INDEX_VERSION", "v1")

    def _get_folder_key(self, tenant_id: str, engagement_id: str, folder_path: str):
        """
        Generate Firestore Document ID for a folder
        Format: {tenant}__{engagement}__{hash(path)}
        """
        normalized_path = folder_path.strip()
        if not normalized_path.startswith("/"): normalized_path = "/" + normalized_path
        if not normalized_path.endswith("/"): normalized_path = normalized_path + "/"
            
        path_hash = hashlib.sha256(normalized_path.encode('utf-8')).hexdigest()[:16]
        return f"{tenant_id}__{engagement_id}__{path_hash}", normalized_path

    def _add_to_cache(self, tenant_id: str, engagement_id: str, profile_data: Dict[str, Any]):
        """
        문서 정보를 바탕으로 트리 구조(파일, 폴더)를 메모리 캐시에 구성
        """
        doc_id = profile_data.get("doc_id")
        title = profile_data.get("title", "Untitled")
        folder_path = profile_data.get("folder_path", "/")
        
        # [Fix] Data Correction: If folder_path looks like a file (ends with extension), strip the filename.
        # This fixes the issue where files are shown as folders in the tree.
        clean_path = folder_path.rstrip("/")
        # Common extensions check
        if clean_path.lower().endswith(('.pdf', '.docx', '.xlsx', '.pptx', '.txt', '.jpg', '.png', '.jpeg')):
            if "/" in clean_path:
                folder_path = clean_path.rsplit("/", 1)[0]
            else:
                folder_path = "/"
            # logger.warning(f"Corrected suspicious folder path: {clean_path} -> {folder_path}")

        # Normalize
        if not folder_path.startswith("/"): folder_path = "/" + folder_path
        if not folder_path.endswith("/"): folder_path += "/"
        
        # 1. 문서가 속한 폴더(Parent) 처리
        folder_key, normalized_path = self._get_folder_key(tenant_id, engagement_id, folder_path)
        
        if folder_key not in self.tree_cache:
            self.tree_cache[folder_key] = {
                "tenant_id": tenant_id, "engagement_id": engagement_id, "folder_path": normalized_path,
                "children_docs": [], "children_folders": set(), "doc_ids": set()
            }
            
        # Add Doc to Folder Cache
        # [Fix] 중복 방지
        if doc_id and doc_id not in self.tree_cache[folder_key]["doc_ids"]:
            doc_info = {
                "doc_id": doc_id,
                "title": title,
                "modified_time": profile_data.get("modified_time"),
                "review_status": profile_data.get("review_status", ReviewStatus.PENDING.value),
                "security_level": profile_data.get("security_level", SecurityLevel.LOW.value),
            }
            self.tree_cache[folder_key]["children_docs"].append(doc_info)
            self.tree_cache[folder_key]["doc_ids"].add(doc_id)

        # 2. 상위 폴더 계층 구조 만들기 (Recursive Path Generation)
        parts = [p for p in normalized_path.split("/") if p]
        
        # Root Folder Init
        root_key, _ = self._get_folder_key(tenant_id, engagement_id, "/")
        if root_key not in self.tree_cache:
            self.tree_cache[root_key] = {
                "tenant_id": tenant_id, "engagement_id": engagement_id, "folder_path": "/",
                "children_docs": [], "children_folders": set(), "doc_ids": set()
            }
            
        parent_key = root_key
        parent_path = "/"
        
        for part in parts:
            child_path = parent_path + part + "/"
            child_key, _ = self._get_folder_key(tenant_id, engagement_id, child_path)
            
            # Ensure Child Folder Cache Exists
            if child_key not in self.tree_cache:
                self.tree_cache[child_key] = {
                    "tenant_id": tenant_id, "engagement_id": engagement_id, "folder_path": child_path,
                    "children_docs": [], "children_folders": set(), "doc_ids": set()
                }
            
            # Parent에게 Child 폴더 등록 (Set으로 중복 관리)
            if parent_key in self.tree_cache:
                self.tree_cache[parent_key]["children_folders"].add((part, child_path))
            
            # Move down
            parent_key = child_key
            parent_path = child_path

    def flush_to_firestore(self, mode="overwrite"):
        """
        메모리 캐시 내용을 Firestore에 저장
        mode="overwrite": 캐시 내용으로 덮어씀 (refresh_all용)
        mode="merge": 기존 내용을 읽어서 병합 (process_single_doc용 - 비효율적이지만 안전)
        """
        batch = self.db.batch()
        count = 0
        total_updates = 0
        
        for key, data in self.tree_cache.items():
            ref = self.db.collection("tree_index").document(key)
            
            # [CRITICAL UPDATE]
            # 단일 문서 업데이트 시 기존 데이터를 날리지 않기 위해
            # 여기서는 'refresh_all' (overwrite) 모드만 안전하게 지원하거나,
            # 아니면 Transaction을 써야 함.
            # 지금은 구조상 refresh_all을 권장하므로 overwrite 로직을 유지하되,
            # process_single_doc에서는 refresh_all을 트리거하도록 변경함.
            
            c_docs = sorted(data["children_docs"], key=lambda x: x.get("title", ""))[:self.docs_per_folder_cap]
            
            c_folders = []
            for name, path in sorted(list(data["children_folders"])):
                c_folders.append({"name": name, "path": path, "updated_at": datetime.now().isoformat()})
                
            payload = {
                "tenant_id": data["tenant_id"],
                "engagement_id": data["engagement_id"],
                "folder_path": data["folder_path"],
                "version": self.version,
                "updated_at": firestore.SERVER_TIMESTAMP,
                "children_folders": c_folders,
                "children_docs": c_docs,
                "has_more_docs": len(data["children_docs"]) > self.docs_per_folder_cap
            }
            
            batch.set(ref, payload, merge=True)
            count += 1
            if count >= 400:
                batch.commit()
                total_updates += count
                count = 0
                batch = self.db.batch()
                
        if count > 0:
            batch.commit()
            total_updates += count
            
        logger.info(f"✅ [TreeIndex] Updated {total_updates} folder nodes.")
        self.tree_cache.clear()

    def process_single_doc(self, profile_data: Dict[str, Any]):
        """
        단일 문서 변경 시 트리 업데이트.
        [Safety] 기존 데이터 유실 방지를 위해, 해당 Tenant의 전체 트리를 재구성하는 것이 안전함.
        문서 양이 많아지면 비효율적이지만, 데이터 무결성이 우선임.
        """
        if not profile_data: return
        t = profile_data.get("tenant_id")
        e = profile_data.get("engagement_id")
        
        logger.info(f"🔄 Triggering Full Tree Refresh for {t}/{e} due to single doc update.")
        self.refresh_all(t, e)

    def refresh_all(self, tenant_id: str, engagement_id: str):
        """전체 재구성 (Batch Job용)"""
        logger.info(f"Refreshing Tree Index for {tenant_id}/{engagement_id}")
        
        # 1. Clear existing cache just in case
        self.tree_cache.clear()
        
        # 2. Fetch ALL profiles
        query = (self.db.collection("profiles")
                 .where("tenant_id", "==", tenant_id)
                 .where("engagement_id", "==", engagement_id)
                 .where("active", "==", True) # Only active docs
                 .stream())
                 
        # 3. Rebuild Memory Tree
        count = 0
        for doc in query:
            self._add_to_cache(tenant_id, engagement_id, doc.to_dict())
            count += 1
            
        # [Fallback] If no profiles found, try 'files' collection to support pre-ingestion files
        if count == 0:
            logger.info(f"No profiles found for {tenant_id}. Fallback to 'files' collection for tree structure.")
            try:
                # Attempt to find files for this tenant
                # Note: 'files' collection must have tenant_id/engagement_id indexed
                files_query = (self.db.collection("files")
                             .where("tenant_id", "==", tenant_id)
                             .where("engagement_id", "==", engagement_id)
                             .where("trashed", "==", False) # Exclude trashed if possible
                             .stream())
                
                for f in files_query:
                    data = f.to_dict()
                    # Map 'files' data to profile schema
                    mapped_data = {
                        "doc_id": data.get("file_id", f.id),
                        "title": data.get("name", "Untitled"),
                        "folder_path": data.get("virtual_path", "/"), # Key Field
                        "modified_time": data.get("updatedAt"),
                        "review_status": "pending",
                        "security_level": "low"
                    }
                    self._add_to_cache(tenant_id, engagement_id, mapped_data)
                    count += 1
                    
            except Exception as e:
                logger.warning(f"Fallback scan failed: {e}")

            
        # 4. Flush (Overwrite)
        self.flush_to_firestore(mode="overwrite")
        logger.info(f"Tree Refresh Complete. Processed {count} profiles.")
