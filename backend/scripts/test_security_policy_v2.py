import os
import sys
import json
from typing import Dict, Any, List

# Setup path to import app modules
# Setup path to import app modules
current_dir = os.path.dirname(os.path.abspath(__file__)) # .../backend/scripts
backend_dir = os.path.dirname(current_dir) # .../backend
sys.path.append(backend_dir)

# Set Env Var for V2
os.environ["SECURITY_POLICY_VERSION"] = "v2"
os.environ["SSOT_EXPLAIN_MODE"] = "rule_only" # Rule only for strict test

from app.rag.steps.classify_doc_policy import PolicyClassifier

def run_test_cases():
    print("\n🔒 [Test] Security Policy V2 Verification\n" + "="*50)
    
    classifier = PolicyClassifier()
    if classifier.policy_version != "v2":
        print("❌ Error: V2 Policy not loaded. Check rules file.")
        return

    test_cases = [
        # Case 1: Standard Template (Medium Base)
        {
            "id": "CASE-01",
            "desc": "Standard Template Folder (Base: Medium)",
            "profile": {
                "folder_path": "/회사공유/표준서식/인사",
                "title": "표준근로계약서_양식_v1.docx",
                "permissions_summary": {"anyone_can_read": False}
            },
            "text": "이 문서는 표준 근로계약서 양식입니다. 내용을 채워 사용하세요."
        },
        # Case 2: Client Tax Data + BRN Pattern (High Raise)
        {
            "id": "CASE-02",
            "desc": "Client Tax Data + BRN Pattern (Base: High -> High)",
            "profile": {
                "folder_path": "/Clients/2024/G electronics/Tax",
                "title": "2024_VAT_Filings.pdf",
                "permissions_summary": {"anyone_can_read": False}
            },
            "text": "사업자등록번호: 123-45-67890 (주)지에전자의 2024년 1기 부가가치세 신고 내역입니다."
        },
        # Case 3: Market Research + Public Shared (Low Base -> Cap Medium)
        {
            "id": "CASE-03",
            "desc": "Market Research + Public Shared (Base: Low -> Cap: Medium likely if Base was High, but here Base is Low so stays Low? Wait, cap is MAX. So Low stays Low. Let's make Base High to test Cap.) -> Let's test standard public doc.",
            "profile": {
                "folder_path": "/공용/리서치/반도체시장",
                "title": "2025_Semiconductor_Trends.pdf",
                "permissions_summary": {"anyone_can_read": True}
            },
            "text": "Global semiconductor market outlook for 2025."
        },
        # Case 3-1: High Base + Public Shared (Cap Test)
        {
            "id": "CASE-03-B",
            "desc": "Client Data + Public Shared (Base: High -> Cap: Medium)",
            "profile": {
                "folder_path": "/Clients/Secret_Project",
                "title": "Leaked_Report.pdf",
                "permissions_summary": {"anyone_can_read": True}
            },
            "text": "This is a secret project report."
        },
        # Case 4: HR Sensitive Keyword (High Raise)
        {
            "id": "CASE-04",
            "desc": "HR Sensitive Keyword (Base: Low -> Raise: High)",
            "profile": {
                "folder_path": "/Personal/Drafts",
                "title": "memo.txt",
                "permissions_summary": {"anyone_can_read": False}
            },
            "text": "이번 연봉 협상 결과를 공유합니다. 김철수: 5000만원, 이영희: 6000만원."
        },
        # Case 5: NDA/Confidential (High Raise)
        {
            "id": "CASE-05",
            "desc": "NDA/Confidential (Base: Low -> Raise: High)",
            "profile": {
                "folder_path": "/General/Agreements",
                "title": "Vendor_Agreement.pdf",
                "permissions_summary": {"anyone_can_read": False}
            },
            "text": "This Non-Disclosure Agreement (NDA) is entered into by..."
        },
        # Case 6: No Text (Scan Fail) -> Base Only
        {
            "id": "CASE-06",
            "desc": "No Text/Scan Fail (Base Only)",
            "profile": {
                "folder_path": "/Clients/Audit/2024/Evidence",
                "title": "scanned_invoice_001.jpg",
                "permissions_summary": {"anyone_can_read": False}
            },
            "text": "" # Empty text
        }
    ]

    for case in test_cases:
        print(f"\n🔹 [{case['id']}] {case['desc']}")
        
        # Run V2 Logic directly
        level, signals, explain_seed = classifier.compute_security_decision_v2(
            case['profile'], 
            case['text']
        )
        
        # Simulate Reason Generation (Rule-only)
        # In real code this is in PolicyClassifier.process_single_document or SecurityExplainer
        # We'll just use the raw signals here to verify
        
        print(f"   👉 Final Level: {level}")
        print(f"   📝 Explain Seed: {explain_seed}")
        print(f"   🔎 Signals ({len(signals)}):")
        for s in signals:
            print(f"      - [{s['source']}] {s['name']}: {s['evidence']} (Delta: {s['delta']})")

    print("\n" + "="*50 + "\n✅ Test Complete")

if __name__ == "__main__":
    run_test_cases()
