
import os
import sys
from google.cloud import firestore
from dotenv import load_dotenv

# .env 로드
base_path = os.path.dirname(os.path.abspath(__file__))
backend_path = os.path.dirname(os.path.dirname(base_path)) # backend/
load_dotenv(os.path.join(backend_path, '.env'))

def debug_latest_profile():
    project_id = os.getenv("GCP_PROJECT_ID")
    if not project_id:
        print("❌ GCP_PROJECT_ID not set")
        return

    print(f"📡 Connecting to {project_id}...")
    db = firestore.Client(project=project_id)
    
    # Get 1 recent profile
    docs = db.collection("profiles").limit(5).stream()
    
    found = False
    for doc in docs:
        found = True
        data = doc.to_dict()
        print("\n" + "="*40)
        print(f"🆔 Doc ID: {doc.id}")
        print(f"📄 Title  : {data.get('title')}")
        print(f"📂 Folder Path (DB): '{data.get('folder_path')}'")  # [핵심] 따옴표로 감싸서 공백/슬래시 확인
        print("-" * 40)
        
    if not found:
        print("❌ No profiles found.")

if __name__ == "__main__":
    debug_latest_profile()
