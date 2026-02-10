
import os
import sys
import asyncio
import logging

# Add backend to path
sys.path.append(os.path.join(os.getcwd(), "backend"))

# Setup Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("GraphTest")

from app.core.gcp_clients import get_firestore_client
from app.core.config import settings
from app.services.graph_query_service import GraphQueryService
from app.services.firestore_repo import FirestoreRepo
from app.common.types import AuthContext

def get_valid_concept_id():
    db = get_firestore_client()
    docs_ref = (db.collection("graph_serving_docs")
                .limit(20)
                .stream())
    
    for d in docs_ref:
        data = d.to_dict()
        top_c = data.get("top_concepts")
        if top_c:
            return top_c[0].get("concept_id"), top_c[0].get("name")
    return None, None

async def test_expansion():
    cid, cname = get_valid_concept_id()
    if not cid:
        logger.error("Could not find any valid concept to test.")
        return

    logger.info(f"Testing Expansion for Concept: {cid} ({cname})")
    
    logger.info(f"Settings Scope: Tenant={settings.TENANT_ID}, Engagement={settings.ENGAGEMENT_ID}")
    
    # Mock Auth Context
    class MockAuth:
        def __init__(self):
            self.tenant_id = "my-tenant"
            self.engagement_id = "eng-001"
            self.user_id = "test-user"
            self.roles = ["admin"]
            
    auth = MockAuth()
    repo = FirestoreRepo(auth_ctx=auth)
    
    # Debug Repo directly
    logger.info(f"--- Repo Debug ---")
    logger.info(f"Repo Scope: tenant={repr(repo.tenant_id)}, engagement={repr(repo.engagement_id)}")
    
    raw_neighbor = repo.get_concept_neighbors(cid)
    if raw_neighbor:
        logger.info(f"Repo found neighbor data. Keys: {list(raw_neighbor.keys())}")
    else:
        logger.error(f"Repo returned None for {cid}!")
        # Fetch raw to see why
        raw_ref = repo.db.collection("graph_serving_concepts").document(cid).get()
        if raw_ref.exists:
            rd = raw_ref.to_dict()
            t = rd.get('tenant_id')
            e = rd.get('engagement_id')
            logger.info(f"Raw Firestore Data: tenant={repr(t)}, engagement={repr(e)}")
            
            # Check equality
            logger.info(f"Check Tenant: {t} == {repo.tenant_id} -> {t == repo.tenant_id}")
            logger.info(f"Check Engagement: {e} == {repo.engagement_id} -> {e == repo.engagement_id}")
        else:
            logger.error("Raw document does not exist!")
            
    service = GraphQueryService(repo=repo)
    
    # Call expand
    result = service.expand_neighborhood(cid, "concept", doc_limit=50)
    
    nodes = result.get("nodes", [])
    edges = result.get("links", [])
    
    logger.info(f"Result: {len(nodes)} nodes, {len(edges)} edges")
    
    doc_nodes = [n for n in nodes if n.get("group") == "document"]
    concept_nodes = [n for n in nodes if n.get("group") == "concept"]
    
    logger.info(f"Docs: {len(doc_nodes)}, Concepts: {len(concept_nodes)}")
    
    if len(doc_nodes) > 0:
        logger.info("✅ Docs found in expansion!")
        for d in doc_nodes[:5]:
            logger.info(f"   - Doc: {d.get('label')} ({d.get('id')})")
    else:
        logger.error("❌ No docs found! 3-hop failed (or 1-hop failed).")

if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    loop.run_until_complete(test_expansion())
