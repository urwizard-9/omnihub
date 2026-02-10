import os
import sys
import logging
import asyncio
from typing import List

# 백엔드 경로 설정
current_dir = os.path.dirname(os.path.abspath(__file__))
backend_dir = os.path.dirname(current_dir)
sys.path.insert(0, backend_dir)

from dotenv import load_dotenv
load_dotenv()

# 로거 설정
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("RAG_DEBUG")

from app.rag.retriever import Retriever
from app.rag.generator import Generator
from app.services.firestore_repo import FirestoreRepo
from app.core.gcp_clients import get_firestore_client
from app.common.schemas import Evidence
from app.common.types import AuthContext

async def run_debug_session(query: str):
    print(f"\n{'='*60}")
    print(f"🧐 [DEBUG START] Query: {query}")
    print(f"{'='*60}\n")

    # 1. Initialize Components
    try:
        db = get_firestore_client()
        
        # [New] AuthContext Mock (From .env or hardcoded test values)
        tenant_id = os.getenv("TENANT_ID", "my-tenant")
        engagement_id = os.getenv("ENGAGEMENT_ID", "eng-001")
        
        auth_ctx = AuthContext(
            user_id="debug-user",
            tenant_id=tenant_id,
            engagement_id=engagement_id,
            roles=["admin"]
        )
        
        repo = FirestoreRepo(auth_ctx)
        retriever = Retriever(repo)
        generator = Generator()
        print(f"✅ Components Initialized Successfully (Tenant: {tenant_id})")
    except Exception as e:
        print(f"❌ Component Init Failed: {e}")
        return

    # 2. Retrieve Step
    print(f"\n🔍 [Step 1] Retrieving Documents...")
    chunks = []
    try:
        # Top K를 넉넉하게 5개로 설정 (검색 되는지 보기 위해)
        chunks = retriever.retrieve(query, top_k=5)
        
        print(f"   -> Found {len(chunks)} chunks.")
        
        if not chunks:
            print("   ⚠️ No chunks found! (Vector Search returned nothing)")
            print("   (TIP: Check if documents are indexed in Vector Search and metadata exists in Firestore)")
        else:
            for i, chunk in enumerate(chunks):
                # Pydantic v2 dump (or just access fields)
                title = chunk.title or "Untitled"
                score = chunk.relevance if chunk.relevance is not None else 0.0
                snippet = chunk.snippet or ""
                ssot = chunk.ssot_score
                
                print(f"   [{i+1}] Doc: {title} | Score: {score:.4f} | SSOT: {ssot}")
                print(f"       Snippet: {snippet[:100].replace('\n', ' ')}...")

    except Exception as e:
        print(f"❌ Retrieval Failed: {e}")
        import traceback
        traceback.print_exc()
        return

    # 3. Generate Step
    print(f"\n🤖 [Step 2] Generating Answer...")
    try:
        # Schema conversion (Evidence -> Dict)
        chunk_dicts = [c.model_dump() for c in chunks]
        
        answer = generator.generate(query, chunk_dicts)
        print(f"\n{'='*20} [FINAL ANSWER] {'='*20}")
        print(answer)
        print(f"{'='*56}")
        
    except Exception as e:
        print(f"❌ Generation Failed: {e}")


if __name__ == "__main__":
    # 테스트할 질문 리스트
    questions = [
        "CCTV 설치 대금은 얼마고 언제 줘?",
        "하자 보수 기간은 몇 년이야?",
        "계약 해지 조건이 뭐야?"
    ]
    
    if len(sys.argv) > 1:
        # 커맨드 라인 인자 (따옴표로 묶어야 함)
        questions = [sys.argv[1]]

    async def main():
        for q in questions:
            await run_debug_session(q)

    # Windows SelectorPolicy fix for asyncio (if needed)
    if sys.platform == 'win32':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
        
    asyncio.run(main())
