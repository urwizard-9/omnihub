import os
import logging
from typing import List, Dict, Any, Optional
from fastapi import HTTPException
from app.common.enums import SecurityLevel, ReviewStatus
from app.common.types import AuthContext

# Logger
logger = logging.getLogger("PermissionGuard")
logger.setLevel(os.getenv("LOG_LEVEL", "INFO").upper())

class PermissionGuard:
    """
    Centralized Permission & Security Guard Layer.
    Enforces Tenant/Engagement isolation and Document Security Policies.
    """
    
    @staticmethod
    def _is_admin_or_reviewer(auth_ctx: AuthContext) -> bool:
        # auth_ctx.roles가 list라고 가정
        roles = auth_ctx.roles
        return "admin" in roles or "reviewer" in roles

    @staticmethod
    def _check_scope(auth_ctx: AuthContext, doc: Dict[str, Any]) -> bool:
        """
        Tenant & Engagement Isolation Check (Strict)
        """
        # Document's tenant/engagement
        doc_tenant = doc.get("tenant_id")
        doc_engagement = doc.get("engagement_id")
        
        # User's context
        user_tenant = auth_ctx.tenant_id
        user_engagement = auth_ctx.engagement_id
        
        # 1. Tenant Mismatch -> BLOCK
        if doc_tenant and doc_tenant != user_tenant:
            return False
            
        # 2. Engagement Mismatch -> BLOCK
        # (Engagement가 없는 공통 문서는 허용할 수도 있으나, 여기선 엄격하게 격리)
        if doc_engagement and doc_engagement != user_engagement:
             return False
             
        return True

    @classmethod
    def ensure_doc_access(cls, auth_ctx: AuthContext, doc: Dict[str, Any]):
        """
        Check access for a single document. Raise 403 if denied.
        """
        # 1. Scope Check
        if not cls._check_scope(auth_ctx, doc):
            logger.warning(f"Access Denied (Scope Mismatch): User={auth_ctx.user_id}, Doc={doc.get('doc_id')}")
            raise HTTPException(status_code=403, detail="Permission Denied: Scope Mismatch")
            
        is_privileged = cls._is_admin_or_reviewer(auth_ctx)

        # 2. Status Check
        status = doc.get("review_status", ReviewStatus.PENDING.value)
        if status != ReviewStatus.APPROVED.value:
            # Only admin/reviewer can see non-approved docs
            if not is_privileged:
                raise HTTPException(status_code=403, detail="Permission Denied: Document not approved")
        
        # 3. Security Level Check
        # High Security Level -> Viewer 접근 차단 (운영 정책 반영)
        sec_level = SecurityLevel.normalize(doc.get("security_level")).value
        if sec_level == SecurityLevel.HIGH.value:
            if not is_privileged:
                 raise HTTPException(status_code=403, detail="Permission Denied: High Security Level (View Restricted)")

        return True

    @classmethod
    def filter_docs(cls, auth_ctx: AuthContext, docs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Filter a list of documents based on permission rules.
        Used for Search Results, Tree View, etc.
        """
        allowed = []
        is_privileged = cls._is_admin_or_reviewer(auth_ctx)
        
        for doc in docs:
            # 1. Scope Check
            if not cls._check_scope(auth_ctx, doc):
                continue
                
            # 2. Status Check
            status = doc.get("review_status", ReviewStatus.PENDING.value)
            if status != ReviewStatus.APPROVED.value and not is_privileged:
                continue
                
            # 3. Security Level Check
            sec_level = SecurityLevel.normalize(doc.get("security_level")).value
            if sec_level == SecurityLevel.HIGH.value and not is_privileged:
                continue
            
            allowed.append(doc)
            
        return allowed

    @classmethod
    def filter_graph_payload(cls, auth_ctx: AuthContext, nodes: List[Dict], edges: List[Dict]) -> Dict[str, List]:
        """
        Filter Graph Nodes & Edges preventing data leakage.
        
        Strategy:
        1. Filter 'document' nodes based on permissions.
        2. Keep 'concept' nodes ONLY if they are connected to at least one visible document.
           (This prevents leaking concepts that solely belong to restricted documents)
        3. Filter 'edges' where both endpoints are visible.
        """
        doc_nodes = []
        concept_nodes = []
        other_nodes = []
        
        # 1. Separate Nodes by Type (GraphQueryService uses "group": "document" or "concept")
        # Fallback to "type" if "group" is missing.
        for node in nodes:
            ntype = node.get("group", node.get("type", "unknown"))
            if ntype == "document":
                doc_nodes.append(node)
            elif ntype == "concept":
                concept_nodes.append(node)
            else:
                other_nodes.append(node)
                
        # 2. Filter Document Nodes (Strict Permission Check)
        # Note: doc nodes from GraphService usually strictly follow document schema or are valid doc objects.
        # But filter_docs expects specific fields (tenant_id, etc.).
        # If GraphService returns simplified nodes, we might need to ensure fields exist.
        # Assuming GraphService returns full doc info or enough for checks.
        
        # Admin can see all, but scope check is still needed? 
        # filter_docs handles scope check internally.
        allowed_doc_nodes = cls.filter_docs(auth_ctx, doc_nodes)
        allowed_doc_ids = {n.get("id") for n in allowed_doc_nodes}
        
        # 3. Filter Concept Nodes based on Visibility (Leakage Prevention)
        # Identify concepts connected to Allowed Docs
        visible_concept_ids = set()
        
        for edge in edges:
            src = edge.get("source")
            tgt = edge.get("target")
            
            # Check Connections
            # Case A: Doc -> Concept
            if src in allowed_doc_ids:
                visible_concept_ids.add(tgt)
            # Case B: Concept -> Doc
            if tgt in allowed_doc_ids:
                visible_concept_ids.add(src)
                
        # Filter concepts
        allowed_concept_nodes = []
        for c_node in concept_nodes:
            # Concepts usually don't have tenant/engagement fields in the node payload directly 
            # if they come from graph_serving_concepts (which aggregates).
            # But checking connection visibility is safer for leakage prevention.
            # However, if concept is global (shared), is it safe?
            # Yes, if it's connected to a visible doc, user has context to see it.
            if c_node.get("id") in visible_concept_ids:
                allowed_concept_nodes.append(c_node)
        
        # 4. Filter Edges
        final_allowed_nodes = allowed_doc_nodes + allowed_concept_nodes + other_nodes
        final_node_ids = {n.get("id") for n in final_allowed_nodes}
        
        allowed_edges = []
        for edge in edges:
            if edge.get("source") in final_node_ids and edge.get("target") in final_node_ids:
                allowed_edges.append(edge)
                
        return {
            "nodes": final_allowed_nodes, 
            "edges": allowed_edges
        }

    @classmethod
    def ensure_download_allowed(cls, auth_ctx: AuthContext, doc: Dict[str, Any]):
        """
        Check if file download is permitted.
        """
        # 1. Basic Access Check first (View 권한 선행)
        if not cls.ensure_doc_access(auth_ctx, doc): # ensure_doc_access raises, but returns True on success
             return False
        
        # 2. Strict Download Policy for High Security
        sec_level = SecurityLevel.normalize(doc.get("security_level")).value
        if sec_level == SecurityLevel.HIGH.value:
            if not cls._is_admin_or_reviewer(auth_ctx):
                raise HTTPException(status_code=403, detail="Permission Denied: High Security Download Restricted")
                
        return True

if __name__ == "__main__":
    # Smoke Test
    print("Running PermissionGuard Smoke Test...")
    
    # Mock Objects
    ctx_viewer = AuthContext(
        user_id="viewer", tenant_id="t1", engagement_id="e1", roles=["viewer"],
        request_id="req1", trace_id="tr1", timestamp=0.0
    )
    ctx_admin = AuthContext(
        user_id="admin", tenant_id="t1", engagement_id="e1", roles=["admin"],
        request_id="req2", trace_id="tr2", timestamp=0.0
    )
    
    doc_approved_low = {
        "doc_id": "d1", "tenant_id": "t1", "engagement_id": "e1",
        "review_status": ReviewStatus.APPROVED.value, "security_level": SecurityLevel.LOW.value
    }
    doc_approved_high = {
        "doc_id": "d2", "tenant_id": "t1", "engagement_id": "e1",
        "review_status": ReviewStatus.APPROVED.value, "security_level": SecurityLevel.HIGH.value
    }
    doc_pending = {
        "doc_id": "d3", "tenant_id": "t1", "engagement_id": "e1",
        "review_status": ReviewStatus.PENDING.value, "security_level": SecurityLevel.LOW.value
    }
    doc_mismatch = {
        "doc_id": "d4", "tenant_id": "t2", "engagement_id": "e1"
    }

    # Test Cases
    try:
        # 1. Regular View (Success)
        PermissionGuard.ensure_doc_access(ctx_viewer, doc_approved_low)
        print("PASS: Viewer View Low Approved")
        
        # 2. High Security View (Viewer -> Fail)
        try:
            PermissionGuard.ensure_doc_access(ctx_viewer, doc_approved_high)
            print("FAIL: Viewer should NOT view High doc")
        except HTTPException:
            print("PASS: Viewer blocked from High doc")
            
        # 3. High Security View (Admin -> Success)
        PermissionGuard.ensure_doc_access(ctx_admin, doc_approved_high)
        print("PASS: Admin View High Approved")

        # 4. Pending View (Viewer -> Fail)
        try:
            PermissionGuard.ensure_doc_access(ctx_viewer, doc_pending)
            print("FAIL: Viewer should NOT view Pending doc")
        except HTTPException:
            print("PASS: Viewer blocked from Pending doc")

        # 5. Pending View (Admin -> Success)
        PermissionGuard.ensure_doc_access(ctx_admin, doc_pending)
        print("PASS: Admin View Pending doc")
        
        # 6. Scope Mismatch (Fail)
        try:
            PermissionGuard.ensure_doc_access(ctx_admin, doc_mismatch)
            print("FAIL: Mismatch scope should block")
        except HTTPException:
            print("PASS: Mismatch scope blocked")

        print("ALL SMOKE TESTS PASSED")
    except Exception as e:
        print(f"SMOKE TEST FAILED: {e}")
