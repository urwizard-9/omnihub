"""
그래프 재구축 스크립트
======================
락 병목으로 SKIP된 개념 표준화를 전체 문서 대상으로 다시 실행합니다.

실행:
  cd backend
  python -m scripts.dev.rebuild_graph
"""

import os
import sys
import time
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed

# 프로젝트 루트를 PYTHONPATH에 추가
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from dotenv import load_dotenv
load_dotenv()

from app.core.gcp_clients import get_firestore_client
from app.rag.steps.build_concepts import ConceptBuilder
from app.rag.steps.build_graph_edges import GraphEdgeBuilder
from app.rag.steps.edge_ranker import EdgeRanker
from app.rag.steps.build_graph_serving_index import GraphServingIndexBuilder

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(message)s")
logger = logging.getLogger("GraphRebuilder")

# ── 설정 ──
MAX_WORKERS = 8  # 동시 처리 수 (필요 시 조절)


def get_all_doc_ids():
    """entities 컬렉션에서 처리 가능한 전체 doc_id 목록 조회"""
    db = get_firestore_client()
    docs = db.collection("entities").stream()
    ids = [doc.id for doc in docs]
    logger.info(f"📋 entities 컬렉션에서 {len(ids)}개 문서 ID 발견")
    return ids


def rebuild_concepts(doc_ids: list):
    """Step 1: 개념 표준화 (병렬)"""
    logger.info(f"\n{'='*60}")
    logger.info(f"🧠 [Step 1/4] 개념 표준화 시작 ({len(doc_ids)}개 문서)")
    logger.info(f"{'='*60}")

    builder = ConceptBuilder()
    success, fail = 0, 0
    t0 = time.time()

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = {
            executor.submit(builder.process_single_document, did): did
            for did in doc_ids
        }
        for future in as_completed(futures):
            did = futures[future]
            try:
                future.result()
                success += 1
            except Exception as e:
                fail += 1
                logger.error(f"   ❌ {did}: {e}")

            # 진행률 로그
            total = success + fail
            if total % 20 == 0 or total == len(doc_ids):
                logger.info(f"   진행: {total}/{len(doc_ids)} (성공 {success}, 실패 {fail})")

    elapsed = time.time() - t0
    logger.info(f"✅ 개념 표준화 완료: {success}성공 / {fail}실패 / {elapsed:.1f}초")


def rebuild_edges(doc_ids: list):
    """Step 2: 엣지 재구축 (병렬)"""
    logger.info(f"\n{'='*60}")
    logger.info(f"🔗 [Step 2/4] 엣지 재구축 시작 ({len(doc_ids)}개 문서)")
    logger.info(f"{'='*60}")

    builder = GraphEdgeBuilder()
    success, fail = 0, 0
    t0 = time.time()

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = {
            executor.submit(builder.process_single_document, did): did
            for did in doc_ids
        }
        for future in as_completed(futures):
            did = futures[future]
            try:
                future.result()
                success += 1
            except Exception as e:
                fail += 1
                logger.error(f"   ❌ {did}: {e}")

            total = success + fail
            if total % 20 == 0 or total == len(doc_ids):
                logger.info(f"   진행: {total}/{len(doc_ids)} (성공 {success}, 실패 {fail})")

    elapsed = time.time() - t0
    logger.info(f"✅ 엣지 재구축 완료: {success}성공 / {fail}실패 / {elapsed:.1f}초")


def rebuild_ranks(doc_ids: list):
    """Step 3: 엣지 랭킹 (병렬)"""
    logger.info(f"\n{'='*60}")
    logger.info(f"⚖️ [Step 3/4] 엣지 랭킹 시작 ({len(doc_ids)}개 문서)")
    logger.info(f"{'='*60}")

    ranker = EdgeRanker()
    success, fail = 0, 0
    t0 = time.time()

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = {
            executor.submit(ranker.process_single_document, did): did
            for did in doc_ids
        }
        for future in as_completed(futures):
            did = futures[future]
            try:
                future.result()
                success += 1
            except Exception as e:
                fail += 1
                logger.error(f"   ❌ {did}: {e}")

            total = success + fail
            if total % 20 == 0 or total == len(doc_ids):
                logger.info(f"   진행: {total}/{len(doc_ids)} (성공 {success}, 실패 {fail})")

    elapsed = time.time() - t0
    logger.info(f"✅ 엣지 랭킹 완료: {success}성공 / {fail}실패 / {elapsed:.1f}초")


def rebuild_serving_index():
    """Step 4: 그래프 서빙 인덱스 전체 재구축"""
    logger.info(f"\n{'='*60}")
    logger.info(f"📊 [Step 4/4] 그래프 서빙 인덱스 재구축")
    logger.info(f"{'='*60}")

    t0 = time.time()
    builder = GraphServingIndexBuilder()
    builder.run()  # 전체 재구축 (배치 모드)
    elapsed = time.time() - t0
    logger.info(f"✅ 서빙 인덱스 재구축 완료: {elapsed:.1f}초")


def main():
    total_start = time.time()
    logger.info("🚀 그래프 전체 재구축 시작")

    # 처리할 문서 목록 조회
    doc_ids = get_all_doc_ids()
    if not doc_ids:
        logger.warning("처리할 문서가 없습니다.")
        return

    # 4단계 순차 실행
    rebuild_concepts(doc_ids)    # 1. 개념
    rebuild_edges(doc_ids)       # 2. 엣지
    rebuild_ranks(doc_ids)       # 3. 랭킹
    rebuild_serving_index()      # 4. 서빙 인덱스

    total_elapsed = time.time() - total_start
    logger.info(f"\n{'='*60}")
    logger.info(f"🎉 그래프 전체 재구축 완료! 총 소요시간: {total_elapsed:.1f}초")
    logger.info(f"{'='*60}")


if __name__ == "__main__":
    main()
