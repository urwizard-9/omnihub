
import firebase_admin
from firebase_admin import credentials, firestore
import os
import sys

# Initialize Firestore
cred_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS", "app/_local_secrets/service_account.json")
if not os.path.exists(cred_path):
    print(f"Credential file not found at {cred_path}")
    # Try looking one level up if run from scripts/
    cred_path = "../app/_local_secrets/service_account.json"

try:
    if not firebase_admin._apps:
        cred = credentials.Certificate(cred_path)
        firebase_admin.initialize_app(cred)
    print("Firebase initialized.")
except Exception as e:
    print(f"Firebase init error: {e}")
    sys.exit(1)

db = firestore.client()

# Check a known file ID
file_id = "fil_1VgeYu9J-jga3W1OqDZA__kJ4t9i12FCm"

try:
    print(f"Checking document {file_id}...")
    doc_ref = db.collection('files').document(file_id)
    doc = doc_ref.get()

    if doc.exists:
        data = doc.to_dict()
        print("--- Document Data ---")
        print(f"File ID: {file_id}")
        print(f"Name: {data.get('name', 'N/A')}")
        print(f"AI Status: {data.get('aiStatus', 'N/A')}")
        print(f"GCS URI: {data.get('gcsUri') or data.get('gcs_uri', 'N/A')}")
        print(f"Mime Type: {data.get('mimeType') or data.get('mime_type', 'N/A')}")
        print("---------------------")
    else:
        print(f"File {file_id} not found in Firestore.")

except Exception as e:
    print(f"Error accessing document: {e}")

print("\nListing some pending files:")
try:
    # Use filter compatible with older firebase-admin if needed
    files_ref = db.collection('files')
    query = files_ref.where('aiStatus', '==', 'pending').limit(5)
    docs = query.stream()
    
    count = 0
    for d in docs:
        count += 1
        print(f"- {d.id}: {d.to_dict().get('name', 'N/A')} (Status: {d.to_dict().get('aiStatus')})")
    
    if count == 0:
        print("No pending files found.")

except Exception as e:
    print(f"Error listing pending files: {e}")
