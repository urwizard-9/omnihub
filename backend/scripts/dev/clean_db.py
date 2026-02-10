import firebase_admin
from firebase_admin import credentials, firestore
import logging
from dotenv import load_dotenv
import os

# Logger 설정
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("DB-Cleaner")

# .env 로드
load_dotenv()

def delete_collection(col_ref, batch_size):
    """
    컬렉션 내의 문서를 배치 단위로 삭제합니다. (반복문 사용)
    """
    if batch_size == 0:
        return

    while True:
        docs = list(col_ref.limit(batch_size).stream())
        deleted = 0

        if not docs:
            break

        for doc in docs:
            # logger.info(f"Deleting doc {doc.id} => {doc.reference.path}")
            doc.reference.delete()
            deleted += 1

        if deleted < batch_size:
            break
            
    return

def main():
    # 1. Firebase 초기화 (이미 실행 중이면 건너뜀)
    try:
        # 이미 초기화되었는지 확인
        if not firebase_admin._apps:
            cred_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
            if not cred_path:
                print("❌ GOOGLE_APPLICATION_CREDENTIALS 환경변수가 설정되지 않았습니다.")
                # 로컬 개발 환경에서 ADC(Application Default Credentials)를 사용하는 경우도 고려
                # cred = credentials.ApplicationDefault() 
                # firebase_admin.initialize_app(cred)
                # 여기서는 명시적 키 파일을 우선시합니다.
                return
                 
            cred = credentials.Certificate(cred_path)
            firebase_admin.initialize_app(cred)
    except Exception as e:
        print(f"⚠️ Firebase 초기화 중 경고 (무시 가능): {e}")

    db = firestore.client()
    
    # 2. 삭제할 컬렉션 목록 (RAG 파이프라인 생성 순서 역순 고려X, 단순히 전체 나열)
    collections_to_clear = [
        # --- [Phase 1: Ingestion & Profile] ---
        "files",              # 원본 파일 메타
        "folders",            # 폴더 동기화 상태
        "docai_results",      # Document AI 결과
        "profiles",           # 문서 프로필 (상태 관리)

        # --- [Phase 2: RAG Artifacts] ---
        "chunks",             # 텍스트 청크
        "doc_chunks",         # (Legacy) 혹시 모를 레거시
        "policies",           # 보안 분류 결과
        "cards",              # 문서 카드/요약
        "entities",           # 추출된 엔티티
        "embeddings",         # 벡터 임베딩 메타 (누락되었던 항목)

        # --- [Phase 3: Indexing & Bundling] ---
        "doc_bundles",        # 최종 아티팩트 번들
        "vector_upserts",     # 벡터 DB 업서트 기록
        "documents",          # 서빙용 최종 문서 메타

        # --- [Phase 4: Knowledge Graph] ---
        "concepts",           # 집계된 개념 (누락되었던 항목)
        "concept_maps",       # 개념 매핑 (누락되었던 항목)
        "edges_doc_concept",  # 문서-개념 연결 엣지
        "graph_serving_docs",      # 그래프 서빙 (문서 중심) (누락되었던 항목)
        "graph_serving_concepts",  # 그래프 서빙 (개념 중심) (누락되었던 항목)

        # --- [Phase 5: Tree Structure] ---
        "tree_index",         # 트리 구조 인덱스 (누락되었던 항목)
        
        # --- [Optional: Logs & System] ---
        # "logs",             # 감사 로그 (필요 시 주석 해제)
        # "watch_channels",   # 웹훅 채널 (재설정 필요하므로 주의)
    ]

    print("🔥 [DB Cleaner] 파이프라인 데이터 삭제 시작...")
    print(f"대상 컬렉션: {len(collections_to_clear)}개")
    
    deleted_collections = []

    for col_name in collections_to_clear:
        col_ref = db.collection(col_name)
        
        # 문서가 하나라도 있는지 확인 (비용 절약)
        docs = list(col_ref.limit(1).stream())
        if not docs:
            print(f"   [Skip] {col_name} (비어있음)")
            continue
            
        print(f"   🗑️ Deleting {col_name}...", end=" ", flush=True)
        delete_collection(col_ref, 100)
        print("Done.")
        deleted_collections.append(col_name)
        
    print("\n✨ 모든 데이터 삭제 완료!")
    if deleted_collections:
        print(f"삭제된 컬렉션: {', '.join(deleted_collections)}")
    else:
        print("삭제된 데이터가 없습니다.")

if __name__ == "__main__":
    main()
