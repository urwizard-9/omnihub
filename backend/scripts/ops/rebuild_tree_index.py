
import sys
import os
import argparse
from dotenv import load_dotenv

# .env 로드
base_path = os.path.dirname(os.path.abspath(__file__))
backend_path = os.path.dirname(os.path.dirname(base_path)) # backend/
load_dotenv(os.path.join(backend_path, '.env'))

# Add backend path to sys.path for module import
sys.path.append(backend_path)

from app.services.tree_indexer_service import TreeIndexerService

def rebuild(tenant_id, engagement_id):
    print(f"🚀 Starting Tree Index Rebuild for {tenant_id}/{engagement_id}...")
    
    indexer = TreeIndexerService()
    indexer.refresh_all(tenant_id, engagement_id)
    
    print("✅ Tree Index Rebuild Completed!")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Rebuild Tree Index from Profiles")
    parser.add_argument("--tenant", default="my-tenant", help="Tenant ID")
    parser.add_argument("--engagement", default="eng-001", help="Engagement ID")
    
    args = parser.parse_args()
    
    rebuild(args.tenant, args.engagement)
