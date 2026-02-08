import sys
import os
from google.cloud import firestore

# [통합] Backend Imports
sys.path.append(os.path.join(os.path.dirname(__file__), '../'))

from app.core.gcp_clients import get_firestore_client

def inspect_excel_processing(doc_id):
    db = get_firestore_client()
    
    print(f"🔍 Inspecting Doc ID: {doc_id}")
    
    # 1. File Status Check
    f_ref = db.collection("files").document(doc_id).get()
    if f_ref.exists:
        data = f_ref.to_dict()
        print(f"📁 File Status: {data.get('aiStatus')}")
        print(f"   - Name: {data.get('name')}")
        print(f"   - Page Count: {data.get('pageCount')}")
    else:
        print("❌ File document not found!")
        return

    # 2. DocAI Results (Excel Extractor Output)
    d_ref = db.collection("docai_results").document(doc_id).get()
    if d_ref.exists:
        res = d_ref.to_dict()
        full_text = res.get("full_text", "")
        print(f"📄 Extracted Text Length: {len(full_text)} chars")
        print(f"   - Starts With: {full_text[:100]}...")
    else:
        print("❌ DocAI Results (Excel Output) not found!")

    # 3. Chunks Check
    chunks_ref = db.collection("chunks").where("doc_id", "==", doc_id).stream()
    chunks = list(chunks_ref)
    print(f"🧩 Chunks Count: {len(chunks)}")
    
    if chunks:
        # Inspect first chunk
        first = chunks[0].to_dict()
        print(f"   - Chunk #1 ID: {chunks[0].id}")
        print(f"   - Content Preview: {first.get('content', '')[:150]}...")
        print(f"   - Metadata: {first}")
    else:
        print("❌ No Chunks found! (Chunker failed?)")
        
    # 4. Profile Check (Scope)
    p_ref = db.collection("profiles").document(doc_id).get()
    if p_ref.exists:
        prof = p_ref.to_dict()
        print(f"👤 Profile Scope: Tenant={prof.get('tenant_id')}, Engagement={prof.get('engagement_id')}")
        print(f"   - Active: {prof.get('active')}")
    else:
        print("❌ Profile not found!")

    # 5. Vector Upsert Status
    v_ref = db.collection("vector_upserts").document(doc_id).get()
    if v_ref.exists:
        v_data = v_ref.to_dict()
        print(f"✅ Vector Upserted Count: {v_data.get('upserted_count')}")
        if v_data.get("error"):
            print(f"❌ Vector Error: {v_data.get('error')}")
    else:
        print("❌ No Vector Upsert Record found!")

if __name__ == "__main__":
    target_id = "fil_16dHrfch9CAVGKcP8EAaX3xD_78-erHFi" # 엑셀 파일 ID
    inspect_excel_processing(target_id)
