import sys
import os
import time
import pandas as pd
from google.cloud import storage
from google.cloud import firestore

# [통합] Backend Imports
# Add backend to sys.path
# If running from backend root:
sys.path.append(os.getcwd())
# If running from script dir:
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from app.core.config import settings
from app.core.gcp_clients import get_firestore_client
from app.rag.steps.run_excel_extract import ExcelExtractor

# Mock Excel File Creation
def create_test_excel():
    df = pd.DataFrame({'A': [1, 2, 3], 'B': ['a', 'b', 'c']})
    filename = "test_data.xlsx"
    df.to_excel(filename, index=False)
    return filename

def verify_schema():
    print("🚀 Starting Excel Schema Verification...")
    
    # 1. Setup
    db = get_firestore_client()
    project_id = settings.PROJECT_ID
    bucket_name = getattr(settings, "GCS_BUCKET", f"{project_id}-docai-output")
    storage_client = storage.Client(project=project_id)
    bucket = storage_client.bucket(bucket_name)
    
    # 2. Upload Test File
    local_file = create_test_excel()
    file_id = f"test_excel_{int(time.time())}"
    gcs_uri = f"gs://{bucket_name}/test_setup/{file_id}.xlsx"
    
    blob = bucket.blob(f"test_setup/{file_id}.xlsx")
    blob.upload_from_filename(local_file)
    print(f"✅ Uploaded test file to {gcs_uri}")

    # [Fix] Create dummy file record in Firestore (simulating Ingestion Service)
    db.collection("files").document(file_id).set({
        "name": "test_data.xlsx",
        "human_readable_status": "Uploaded",
        "status": "synced"
    })
    print(f"✅ Created dummy Firestore record for {file_id}")
    
    # 3. Run Extractor
    extractor = ExcelExtractor()
    mime_type = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    
    print("🔄 Running ExcelExtractor...")
    extractor.process_single_document(file_id, gcs_uri, mime_type)
    
    # 4. Verify Firestore
    doc_ref = db.collection("docai_results").document(file_id).get()
    if not doc_ref.exists:
        print("❌ Firestore docai_results not found!")
        return
    
    data = doc_ref.to_dict()
    print("✅ Firestore document found.")
    
    # Keys Check
    required_keys = ["full_text", "pages", "status", "processed_at", "raw_output_uri", "page_count"]
    missing = [k for k in required_keys if k not in data]
    if missing:
        print(f"❌ Missing keys in Firestore: {missing}")
    else:
        print("✅ Firestore schema keys valid.")
        
    # 5. Verify GCS Output
    output_uri = data.get("raw_output_uri")
    print(f"📂 Output URI: {output_uri}")
    
    if not output_uri.startswith("gs://"):
        print("❌ Invalid Output URI format")
        return

    # Download output JSON
    blob_path = output_uri.replace(f"gs://{bucket_name}/", "")
    out_blob = bucket.blob(blob_path)
    if not out_blob.exists():
        print("❌ Output JSON not found in GCS")
        return
        
    import json
    json_content = json.loads(out_blob.download_as_text())
    
    if "full_text" not in json_content or "pages" not in json_content:
        print("❌ Invalid JSON content")
    else:
        print("✅ GCS JSON content valid.")
        print(f"📄 Extracted Text Preview: {json_content['full_text'][:50]}...")

    # Cleanup (Optional)
    os.remove(local_file)
    print("✨ Verification Complete!")

if __name__ == "__main__":
    verify_schema()
