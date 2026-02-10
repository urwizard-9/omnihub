"""
Test FirestoreRepo.get_graph_init() directly
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

from app.core.gcp_clients import get_firestore_client

db = get_firestore_client()

tenant_id = os.getenv("TENANT_ID", "default")
engagement_id = os.getenv("ENGAGEMENT_ID", "default")

print(f"Querying with: tenant={tenant_id}, engagement={engagement_id}")
print()

# Query directly with filters
print("=== graph_serving_concepts (with filter) ===")
cq = (db.collection("graph_serving_concepts")
    .where("tenant_id", "==", tenant_id)
    .where("engagement_id", "==", engagement_id)
    .limit(5)
    .stream())

concepts = []
for c in cq:
    d = c.to_dict()
    cid = d.get("concept_id") or c.id
    top_docs = d.get("top_docs", [])
    concepts.append((cid, len(top_docs)))
    print(f"  Concept: {cid[:30]} | top_docs: {len(top_docs)}")

print(f"\nTotal concepts found: {len(concepts)}")

# Query docs
print("\n=== graph_serving_docs (with filter) ===")
dq = (db.collection("graph_serving_docs")
    .where("tenant_id", "==", tenant_id)
    .where("engagement_id", "==", engagement_id)
    .limit(5)
    .stream())

docs = list(dq)
for d in docs:
    data = d.to_dict()
    print(f"  Doc: {d.id[:30]} | title: {data.get('title', 'N/A')[:30]}")

print(f"\nTotal docs found: {len(docs)}")

# Check sample top_docs content
if concepts:
    print("\n=== Sample top_docs structure ===")
    sample = db.collection("graph_serving_concepts").limit(1).get()[0].to_dict()
    top_docs = sample.get("top_docs", [])
    if top_docs:
        print(f"Sample top_doc: {top_docs[0]}")
    else:
        print("⚠️ top_docs is empty!")
