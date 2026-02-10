#!/usr/bin/env python
"""
특정 문서의 Policy 분류를 재실행하는 스크립트
LLM 설명 생성을 포함하여 재처리합니다.
"""
import os
import sys

# Setup path
current_dir = os.path.dirname(os.path.abspath(__file__))
backend_dir = os.path.dirname(current_dir)
sys.path.insert(0, backend_dir)

from dotenv import load_dotenv
load_dotenv()

print("=" * 50)
print("🔄 Policy Reprocessor")
print("=" * 50)

# Check env vars
print(f"\n📋 현재 설정:")
print(f"   SECURITY_POLICY_VERSION: {os.getenv('SECURITY_POLICY_VERSION')}")
print(f"   SECURITY_EXPLAIN_MODE: {os.getenv('SECURITY_EXPLAIN_MODE')}")
print(f"   SSOT_EXPLAIN_MODE: {os.getenv('SSOT_EXPLAIN_MODE')}")

from app.rag.steps.classify_doc_policy import PolicyClassifier

def reprocess_document(doc_id: str):
    print(f"\n🎯 대상 문서: {doc_id}")
    
    classifier = PolicyClassifier()
    print(f"   Policy Version: {classifier.policy_version}")
    print(f"   Security Explain Mode: {classifier.sec_explain_mode}")
    print(f"   SSOT Explain Mode: {classifier.explain_mode}")
    
    print("\n⏳ 재처리 시작...")
    classifier.process_single_document(doc_id)
    print("\n✅ 완료!")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("\n사용법: python reprocess_policy.py <doc_id>")
        print("예시: python reprocess_policy.py fil_1abc2def3ghi")
        sys.exit(1)
    
    doc_id = sys.argv[1]
    reprocess_document(doc_id)
