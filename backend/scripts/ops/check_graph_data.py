
import sys
import os
from dotenv import load_dotenv
import json

# .env 로드
base_path = os.path.dirname(os.path.abspath(__file__))
backend_path = os.path.dirname(os.path.dirname(base_path)) # backend/
load_dotenv(os.path.join(backend_path, '.env'))
sys.path.append(backend_path)

from app.core.gcp_clients import get_firestore_client

def check_graph_data():
    db = get_firestore_client()
    print("🔍 Checking 'graph_serving_concepts' collection...")
    
    concepts = db.collection("graph_serving_concepts").limit(5).stream()
    
    found_any = False
    for c in concepts:
        found_any = True
        data = c.to_dict()
        cid = c.id
        top_docs = data.get("top_docs", [])
        print(f"\nConcept: {cid}")
        print(f" - Name: {data.get('meta', {}).get('name', 'Unknown')}")
        print(f" - Top Docs Count: {len(top_docs)}")
        
        if top_docs:
            print(f" - Sample Doc: {top_docs[0]}")
        else:
            print(" ⚠️ No linked docs found!")

    if not found_any:
        print("\n❌ No concepts found in DB!")

    print("\n🔍 Checking 'graph_serving_docs' collection...")
    docs = db.collection("graph_serving_docs").limit(5).stream()
    for d in docs:
        data = d.to_dict()
        did = d.id
        top_concepts = data.get("top_concepts", [])
        print(f"\nDoc: {did}")
        print(f" - Title: {data.get('title', 'Unknown')}")
        print(f" - Top Concepts Count: {len(top_concepts)}")

if __name__ == "__main__":
    check_graph_data()
