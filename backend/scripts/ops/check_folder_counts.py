
import os
import sys
from collections import Counter
from google.cloud import firestore
from dotenv import load_dotenv

# .env 로드
base_path = os.path.dirname(os.path.abspath(__file__))
backend_path = os.path.dirname(os.path.dirname(base_path)) # backend/
load_dotenv(os.path.join(backend_path, '.env'))

def check_folder_counts():
    project_id = os.getenv("GCP_PROJECT_ID")
    print(f"📡 Connecting to {project_id}...")
    db = firestore.Client(project=project_id)
    
    print("🔍 Scanning profiles...")
    docs = db.collection("profiles").stream()
    
    # Path Counter
    path_counts = Counter()
    path_samples = {} # Path -> [List of titles]
    
    total_docs = 0
    for doc in docs:
        total_docs += 1
        data = doc.to_dict()
        path = data.get("folder_path", "/")
        title = data.get("title", "Untitled")
        
        path_counts[path] += 1
        
        if path not in path_samples:
            path_samples[path] = []
        if len(path_samples[path]) < 3: # 샘플 3개만 저장
            path_samples[path].append(title)
            
    print(f"\n✅ Total Profiles Scanned: {total_docs}")
    print("\n[Folder File Counts]")
    
    sorted_paths = sorted(path_counts.items(), key=lambda x: x[1], reverse=True)
    
    for path, count in sorted_paths[:20]: # Top 20 folders
        print(f"📂 {path} : {count} files")
        print(f"   Sample: {path_samples[path]}")
        print("-" * 40)
        
    if not sorted_paths:
        print("❌ No profiles found.")

if __name__ == "__main__":
    check_folder_counts()
