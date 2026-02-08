"""
Test GraphQueryService.get_overview() directly
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

from app.common.types import AuthContext
from app.services.graph_query_service import GraphQueryService

# Create mock auth context matching our data
auth_ctx = AuthContext(
    user_id="test-admin",
    tenant_id=os.getenv("TENANT_ID", "default"),
    engagement_id=os.getenv("ENGAGEMENT_ID", "default"),
    roles=["admin"],
    request_id="test-request",
    trace_id="test-trace",
    timestamp=0
)

print(f"Auth Context: tenant={auth_ctx.tenant_id}, engagement={auth_ctx.engagement_id}")
print()

# Test the service
service = GraphQueryService(auth_ctx)
result = service.get_overview(limit=50)

print(f"Nodes: {len(result.get('nodes', []))}")
print(f"Links: {len(result.get('links', []))}")
print()

# Show sample nodes
nodes = result.get('nodes', [])
if nodes:
    print("Sample Nodes:")
    for n in nodes[:5]:
        print(f"  - id: {n.get('id', 'N/A')[:30]}, group: {n.get('group')}, label: {n.get('label', 'N/A')[:30]}")

# Show sample links
links = result.get('links', [])
if links:
    print("\nSample Links:")
    for l in links[:5]:
        src = l.get('source', 'N/A')
        tgt = l.get('target', 'N/A')
        if isinstance(src, dict): src = src.get('id', 'N/A')
        if isinstance(tgt, dict): tgt = tgt.get('id', 'N/A')
        print(f"  - {src[:20]} -> {tgt[:20]}")
else:
    print("\n⚠️ NO LINKS FOUND!")
