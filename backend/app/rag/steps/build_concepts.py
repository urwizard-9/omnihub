import hashlib
import json
import logging
import time
from collections import defaultdict
from google.cloud import storage
from google.cloud import firestore

from app.core.config import settings
from app.core.gcp_clients import get_firestore_client

logger = logging.getLogger("ConceptBuilder")
logger.setLevel(logging.INFO)

class ConceptBuilder:
    def __init__(self):
        self.db = get_firestore_client()
        self.project_id = settings.PROJECT_ID
        self.bucket_name = getattr(settings, "GCS_BUCKET", f"{self.project_id}-docai-output")
        self.bucket = storage.Client(project=self.project_id).bucket(self.bucket_name)
        self.rules_version = getattr(settings, "CONCEPT_RULES_VERSION", "v1")

    def normalize_name(self, name: str) -> str:
        """
        정규화: 소문자, 양옆 공백 제거, 구두점 제거 등 (extract_entities와 동일 규칙)
        """
        if not name: return ""
        import re
        # 소문자 변환 및 양옆 공백 제거
        norm = name.lower().strip()
        # 구두점 제거 (알파벳, 숫자, 공백, 한글 등은 유지하고 특수문자 제거)
        norm = re.sub(r'[^\w\s]', '', norm) 
        # 연속된 공백을 하나로
        norm = re.sub(r'\s+', ' ', norm)
        return norm.strip()

    def generate_concept_id(self, type_str: str, norm_name: str) -> str:
        """MD5 Hash로 고유 ID 생성"""
        raw = f"{type_str}:{norm_name}"
        return hashlib.md5(raw.encode('utf-8')).hexdigest()

    def load_entities_from_gcs(self, gcs_uri: str) -> list:
        """GCS에서 엔티티 리스트 로드"""
        if not gcs_uri: return []
        try:
            blob_path = gcs_uri.replace(f"gs://{self.bucket.name}/", "")
            blob = self.bucket.blob(blob_path)
            raw = blob.download_as_text()
            data = json.loads(raw)
            # [Fix] EntityExtractor saves {doc_id, entities: [], relations: []}, extract 'entities' array
            if isinstance(data, dict):
                return data.get("entities", [])
            elif isinstance(data, list):
                return data  # Legacy: direct list
            return []
        except Exception as e:
            logger.error(f"Failed to load entities from {gcs_uri}: {e}")
            return []

    # ... run_batch ...

    def process_single_document(self, doc_id: str):
        """
        단일 문서에 대한 Concept Incremental Update
        해당 문서의 엔티티만 처리하여 관련 개념 업데이트
        + Concept Map 생성/업데이트 (Edge 생성을 위해 필수)
        """
        logger.info(f"🧠 [Concept] Incremental update for {doc_id}")
        
        # 1. 해당 문서의 엔티티 조회
        ent_ref = self.db.collection("entities").document(doc_id).get()
        if not ent_ref.exists:
            logger.warning(f"SKIP {doc_id}: No entities found")
            return
            
        gcs_uri = ent_ref.get("gcs_entities_uri")
        entities = self.load_entities_from_gcs(gcs_uri)
        
        if not entities:
            logger.warning(f"SKIP {doc_id}: Empty entities list")
            return
        
        tenant = getattr(settings, "TENANT_ID", "default")
        engagement = getattr(settings, "ENGAGEMENT_ID", "default")
        
        # 2. 기존 Concept Map 로드 (병합을 위해)
        # Note: 매번 전체 맵을 로드하는 것은 비효율적일 수 있으나, 현재 구조상 유지
        existing_map = self._load_existing_concept_map()
        
        # 3. 엔티티별 개념 생성/업데이트
        batch = self.db.batch()
        batch_count = 0
        processed_concepts = set()
        new_map_entries = {}
        
        for ent in entities:
            raw_name = ent.get("name")
            type_ = ent.get("type", "OTHERS")
            
            # A. 키/정규화 통일: Priority to concept_key
            concept_key = ent.get("concept_key")
            if concept_key and ":" in concept_key:
                # concept_key format: "TYPE:normalized_name"
                _, norm_name = concept_key.split(":", 1)
            else:
                if not raw_name: continue
                norm_name = self.normalize_name(raw_name)
            
            concept_id = self.generate_concept_id(type_, norm_name)
            
            if concept_id in processed_concepts:
                continue
            processed_concepts.add(concept_id)
            
            # Firestore Read (Current State)
            existing_ref = self.db.collection("concepts").document(concept_id).get()
            
            aliases_set = {raw_name}
            for a in ent.get("aliases", []):
                aliases_set.add(a)
            
            if existing_ref.exists:
                # Update existing concept
                existing_data = existing_ref.to_dict()
                
                # B. doc_frequency 최소 방어
                doc_ids_sample = existing_data.get("doc_ids_sample", [])
                
                should_increment = doc_id not in doc_ids_sample
                
                # Update sample list (Limit 50)
                if should_increment:
                    doc_ids_sample.append(doc_id)
                    if len(doc_ids_sample) > 50:
                        doc_ids_sample.pop(0) # Remove oldest
                
                # Merge aliases
                current_aliases = set(existing_data.get("aliases", []))
                merged_aliases = sorted(list(aliases_set | current_aliases))
                
                update_data = {
                    "aliases": merged_aliases,
                    "last_seen_at": firestore.SERVER_TIMESTAMP,
                    "total_occurrence": firestore.Increment(1),
                    "doc_ids_sample": doc_ids_sample # Update sample list
                }
                
                if should_increment:
                    # [Defense] Increase doc_frequency only if new doc
                    update_data["doc_frequency"] = firestore.Increment(1)
                
                # Map Update (Add new aliases)
                for alias in merged_aliases:
                    norm_alias = self.normalize_name(alias)
                    map_key = f"{type_}:{norm_alias}"
                    new_map_entries[map_key] = concept_id
                    
                batch.set(self.db.collection("concepts").document(concept_id), update_data, merge=True)
                
            else:
                # Create new concept
                concept_data = {
                    "concept_id": concept_id,
                    "tenant_id": tenant,
                    "engagement_id": engagement,
                    "type": type_,
                    "canonical_name": raw_name, # First seen name as canonical
                    "aliases": sorted(list(aliases_set)),
                    "doc_frequency": 1,
                    "total_occurrence": 1,
                    "doc_ids_sample": [doc_id], # Init sample list
                    "last_seen_at": firestore.SERVER_TIMESTAMP,
                    "rules_version": self.rules_version,
                    "active": True
                }
                
                # Map Add
                for alias in sorted(list(aliases_set)):
                    norm_alias = self.normalize_name(alias)
                    map_key = f"{type_}:{norm_alias}"
                    new_map_entries[map_key] = concept_id
                    
                batch.set(self.db.collection("concepts").document(concept_id), concept_data, merge=True)
            
            batch_count += 1
            if batch_count >= 400:
                batch.commit()
                batch = self.db.batch()
                batch_count = 0
        
        if batch_count > 0:
            batch.commit()
        
        # 4. Save merged map
        # Note: This overwrites the map with merged keys. Concurrent updates might conflict here.
        # But for prototype/MVP, this is acceptable as per requirements.
        if new_map_entries:
            # Merge logic: if key exists in existing_map, new value overwrites (usually same)
            # or we respect existing to avoid flip-flop? concept_id is deterministic, so result is same.
            merged_map = {**existing_map, **new_map_entries}
            self.save_concept_map(merged_map)
        
        logger.info(f"✅ [Concept] Updated {len(processed_concepts)} concepts for {doc_id}")
        logger.info(f"   📊 Concept Map: {len(new_map_entries)} updated entries")
    
    def _load_existing_concept_map(self) -> dict:
        """기존 Concept Map 로드 (없으면 빈 dict 반환)"""
        tenant = getattr(settings, "TENANT_ID", "default")
        engagement = getattr(settings, "ENGAGEMENT_ID", "default")
        map_id = f"{tenant}__{engagement}"
        
        try:
            map_ref = self.db.collection("concept_maps").document(map_id).get()
            if not map_ref.exists:
                return {}
            
            gcs_uri = map_ref.get("gcs_uri")
            if not gcs_uri:
                return {}
            
            blob_path = gcs_uri.replace(f"gs://{self.bucket_name}/", "")
            blob = self.bucket.blob(blob_path)
            raw = blob.download_as_text()
            return json.loads(raw)
        except Exception as e:
            logger.warning(f"Failed to load existing concept map: {e}")
            return {}

    def save_concept_map(self, concept_map):
        tenant = getattr(settings, "TENANT_ID", "default")
        engagement = getattr(settings, "ENGAGEMENT_ID", "default")
        map_id = f"{tenant}__{engagement}"
        gcs_path = f"concept_maps/{map_id}/map.json"
        
        blob = self.bucket.blob(gcs_path)
        blob.upload_from_string(json.dumps(concept_map, ensure_ascii=False), content_type="application/json")
        gcs_uri = f"gs://{self.bucket_name}/{gcs_path}"
        
        self.db.collection("concept_maps").document(map_id).set({
            "tenant_id": tenant,
            "engagement_id": engagement,
            "gcs_uri": gcs_uri,
            "entry_count": len(concept_map),
            "updated_at": firestore.SERVER_TIMESTAMP
        }, merge=True)
