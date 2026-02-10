import sys
import os

# Add backend path to sys.path so we can import app modules
# Script is in backend/scripts, so we need to go up one level to backend
current_dir = os.path.dirname(os.path.abspath(__file__))
backend_dir = os.path.dirname(current_dir)
sys.path.append(backend_dir)

import firebase_admin
from firebase_admin import credentials, firestore

# Initialize Firebase (Standalone)
# Since we are running outside of main.py, we need to init manually if not already
try:
    if not firebase_admin._apps:
        # Load .env manually to find creds path? 
        # Or just use the one in app/core/config. But app.core.config might need .env loaded.
        from dotenv import load_dotenv
        load_dotenv(os.path.join(backend_dir, ".env"))
        
        # We need to rely on app.core.gcp_clients to init or do it here.
        # Let's try importing TreeIndexerService which imports gcp_clients
        pass
except Exception as e:
    print(f"Init Warning: {e}")

from app.services.tree_indexer_service import TreeIndexerService
from app.core.gcp_clients import get_firestore_client

def main():
    print("🌲 Starting Manual Tree Index Refresh...")
    
    # 1. Initialize Service
    indexer = TreeIndexerService()
    db = get_firestore_client()
    
    # 2. Identify Tenants (Approximation: use known ones and maybe query profiles)
    # For now, let's hardcode the ones seen in user screenshots and default
    targets = [
        ("default", "default"),
        ("my-tenant", "eng-001"),
        # Add others if needed
    ]
    
    # 3. Refresh
    for tenant_id, engagement_id in targets:
        print(f"\n🔄 Processing {tenant_id} / {engagement_id} ...")
        try:
             indexer.refresh_all(tenant_id, engagement_id)
             print(f"   ✅ Success: {tenant_id}/{engagement_id}")
        except Exception as e:
             print(f"   ❌ Failed: {tenant_id}/{engagement_id} - {e}")

    print("\n🎉 All Done!")

if __name__ == "__main__":
    main()
