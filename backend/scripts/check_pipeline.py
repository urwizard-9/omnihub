import sys
import os
from google.cloud import firestore

# [통합] Backend Imports
sys.path.append(os.path.join(os.path.dirname(__file__), '../'))

from app.core.gcp_clients import get_firestore_client

def check_pipeline_status():
    db = get_firestore_client()
    print("📊 Pipeline Status Check")
    
    docs = db.collection("files").stream()
    
    status_counts = {
        "total": 0,
        "completed": 0,
        "failed": 0,
        "processing": 0,
        "pending": 0,
        "synced": 0 # Initial state
    }
    
    failed_files = []
    
    for doc in docs:
        data = doc.to_dict()
        status = data.get("aiStatus", "unknown")
        
        status_counts["total"] += 1
        status_counts[status] = status_counts.get(status, 0) + 1
        
        if status == "failed":
            failed_reason = data.get("errorMsg", "Unknown Error")
            failed_files.append(f"{doc.id} ({data.get('name')}): {failed_reason}")

    print("-" * 30)
    print(f"Total Files: {status_counts['total']}")
    print(f"✅ Completed: {status_counts.get('completed', 0)}")
    print(f"❌ Failed:    {status_counts.get('failed', 0)}")
    print(f"🔄 Processing:{status_counts.get('processing', 0)}")
    print(f"⏳ Pending:   {status_counts.get('pending', 0)}")
    print(f"📥 Synced:    {status_counts.get('synced', 0)} (Not started)")
    print("-" * 30)
    
    if failed_files:
        print("\n❌ Failed Files Preview (Top 5):")
        for f in failed_files[:5]:
            print(f" - {f}")

if __name__ == "__main__":
    check_pipeline_status()
