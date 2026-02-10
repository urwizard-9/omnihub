
import sys
import os
import argparse
from google.cloud import firestore
from dotenv import load_dotenv

# .env 로드
base_path = os.path.dirname(os.path.abspath(__file__))
backend_path = os.path.dirname(os.path.dirname(base_path)) # backend/
load_dotenv(os.path.join(backend_path, '.env'))
sys.path.append(backend_path)

from app.rag.steps.build_profile import ProfileBuilder
from app.services.tree_indexer_service import TreeIndexerService

def fix_all(tenant_id, engagement_id):
    project_id = os.getenv("GCP_PROJECT_ID")
    print(f"🚀 Starting Full Fix for {tenant_id}/{engagement_id} on {project_id}...")
    
    db = firestore.Client(project=project_id)
    
    # 1. Rebuild Profiles
    print("\n[Phase 1] Rebuilding Profiles with correct Paths...")
    profiler = ProfileBuilder()
    
    # files 컬렉션에서 대상 문서 가져오기
    # (모든 파일을 다 가져와서 Profile을 다시 만듭니다)
    files = db.collection("files").stream()
    count = 0
    for f in files:
        doc_id = f.id
        print(f" -> Processing Profile: {doc_id}", end='\r')
        profiler.process_single_document(doc_id)
        count += 1
        
    print(f"\n✅ Profiles Updated: {count}")
    
    # 2. Rebuild Tree Index
    print("\n[Phase 2] Rebuilding Tree Index...")
    indexer = TreeIndexerService()
    indexer.refresh_all(tenant_id, engagement_id)
    
    print("\n✅ Tree Index Full Rebuild Completed!")

if __name__ == "__main__":
    fix_all("my-tenant", "eng-001")
