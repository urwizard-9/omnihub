import firebase_admin
from firebase_admin import credentials, firestore
import os

# Initialize Firestore
if not firebase_admin._apps:
    cred = credentials.ApplicationDefault()
    firebase_admin.initialize_app(cred, {
        "projectId": "jnu-rise-edu-150",
    })

db = firestore.client()

def check_user_monitored_items():
    print("Listing all users and their monitored items...")
    users_ref = db.collection('users')
    docs = users_ref.stream()

    found = False
    for doc in docs:
        found = True
        data = doc.to_dict()
        email = doc.id
        folders = data.get('monitored_folder_ids', [])
        files = data.get('monitored_file_ids', [])
        print(f"User: {email}")
        print(f"  - Monitored Folders: {folders}")
        print(f"  - Monitored Files: {files}")
        print("-" * 20)

    if not found:
        print("No users found.")

if __name__ == "__main__":
    check_user_monitored_items()
