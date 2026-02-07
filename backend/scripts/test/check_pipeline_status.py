import sys
import os
import argparse
from google.cloud import firestore
from dotenv import load_dotenv

# .env 로드 (상위 폴더 포함 시도)
base_path = os.path.dirname(os.path.abspath(__file__))
backend_path = os.path.dirname(os.path.dirname(base_path)) # backend/
load_dotenv(os.path.join(backend_path, '.env'))

def print_status(icon, name, status, details=""):
    print(f"{icon} {name:<15}: {status:<15} {details}")

def check_pipeline_status(doc_id: str):
    project_id = os.getenv("GCP_PROJECT_ID") or os.getenv("PROJECT_ID")
    if not project_id:
        print("❌ Error: GCP_PROJECT_ID not set in environment.")
        return

    print(f"\n📡 Connecting to Firestore ({project_id})...")
    db = firestore.Client(project=project_id)
    
    # Prefix 보정 (fil_ 접두사 확인)
    if not doc_id.startswith("fil_"):
        print(f"⚠️  Input ID '{doc_id}' does not start with 'fil_'. Checking directly...")
    
    print(f"\n🔍 [Pipeline Status Check] Doc ID: {doc_id}\n" + "="*60)

    # 1. Files (Ingestion)
    file_ref = db.collection("files").document(doc_id).get()
    if not file_ref.exists:
        print(f"❌ Document {doc_id} NOT FOUND in 'files' collection.")
        return

    f_data = file_ref.to_dict()
    print_status("📄", "Files Info", f_data.get("status", "Unknown"), 
                 f"(Name: {f_data.get('name')}, AI: {f_data.get('aiStatus')})")

    # 2. DocAI 
    docai_ref = db.collection("docai_results").document(doc_id).get()
    if docai_ref.exists:
        d_data = docai_ref.to_dict()
        print_status("🤖", "DocAI Result", "Found", f"(Pages: {len(d_data.get('pages', []))})")
    else:
        print_status("🤖", "DocAI Result", "Missing", "")

    # 3. Profiles
    prof_ref = db.collection("profiles").document(doc_id).get()
    if prof_ref.exists:
        p_data = prof_ref.to_dict()
        print_status("�", "Profile", "Found", f"(Active: {p_data.get('active')})")
    else:
        print_status("👤", "Profile", "Missing", "")

    # 4. Chunks
    chunk_ref = db.collection("chunks").document(doc_id).get()
    if chunk_ref.exists:
        c_data = chunk_ref.to_dict()
        print_status("🧩", "Chunks", "Found", f"(Count: {c_data.get('chunk_count')})")
    else:
        print_status("🧩", "Chunks", "Missing", "")

    # 5. Analysis (Parallel Steps)
    # Policy
    pol_ref = db.collection("policies").document(doc_id).get()
    pol_status = "Found" if pol_ref.exists else "Missing"
    print_status("🛡️", "Policy", pol_status, f"(Level: {pol_ref.to_dict().get('security_level') if pol_ref.exists else '-'})")

    # Card
    card_ref = db.collection("cards").document(doc_id).get()
    card_status = "Found" if card_ref.exists else "Missing"
    print_status("🃏", "Card Summary", card_status)

    # Entities
    ent_ref = db.collection("entities").document(doc_id).get()
    ent_status = "Found" if ent_ref.exists else "Missing"
    print_status("�", "Entities", ent_status, f"(Count: {ent_ref.to_dict().get('entity_count') if ent_ref.exists else '-'})")

    # 6. Embeddings
    emb_ref = db.collection("embeddings").document(doc_id).get()
    emb_status = "Found" if emb_ref.exists else "Missing"
    print_status("🧠", "Embeddings", emb_status)

    # 7. Final Document (Vector Serving)
    final_ref = db.collection("documents").document(doc_id).get()
    if final_ref.exists:
        final_data = final_ref.to_dict()
        print_status("✅", "Serving Doc", "READY", f"(Updated: {final_data.get('updated_at')})")
    else:
        print_status("❌", "Serving Doc", "NOT READY", "(Final step missing)")

    print("="*60 + "\n")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Check RAG Pipeline Status for a Document")
    parser.add_argument("doc_id", nargs="?", help="Document ID (e.g. fil_xxxxx)")
    args = parser.parse_args()
    
    target_id = args.doc_id
    if not target_id:
        print("Usage: python check_pipeline_status.py <doc_id>")
        sys.exit(1)
        
    check_pipeline_status(target_id)
