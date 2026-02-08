# OmniHub 프로젝트 아키텍처 분석 문서

> **최종 업데이트**: 2026년 2월 8일
> **버전**: v2.1

---

## 📋 목차

1. [프로젝트 개요](#1-프로젝트-개요)
2. [폴더 구조](#2-폴더-구조)
3. [Backend 상세](#3-backend-상세)
4. [Frontend 상세](#4-frontend-상세)
5. [RAG 파이프라인](#5-rag-파이프라인)
6. [데이터 흐름](#6-데이터-흐름)
7. [Firestore 컬렉션](#7-firestore-컬렉션)
8. [환경 변수](#8-환경-변수)
9. [기술 스택](#9-기술-스택)

---

## 1. 프로젝트 개요

**OmniHub**는 Google Drive 기반 문서 관리 + RAG 검색 + Knowledge Graph 시스템입니다.

### 핵심 기능

| 기능 | 설명 |
|------|------|
| **문서 수집** | Google Drive → GCS 스트리밍, 메타데이터 Firestore 저장 |
| **Document AI** | PDF/이미지 OCR, Excel 직접 파싱 |
| **RAG 검색** | 벡터 검색 + LLM 답변 생성 |
| **Knowledge Graph** | 문서-개념 관계 그래프, 3-Hop 확장 |
| **보안 분류** | Security Level, SSoT Level 자동 분류 |
| **실시간 동기화** | Drive Webhook 변경 감지 |

---

## 2. 폴더 구조

### 2.1 전체 구조
```
omnihub/
├── backend/                    # FastAPI 백엔드
│   ├── app/
│   │   ├── common/             # 공통 스키마/타입
│   │   ├── core/               # 설정, GCP 클라이언트
│   │   ├── models/             # Pydantic 모델
│   │   ├── rag/                # RAG 파이프라인
│   │   │   ├── steps/          # 15개 파이프라인 스텝
│   │   │   └── rules/          # 정책/엔티티 규칙
│   │   ├── routers/            # API 엔드포인트
│   │   ├── services/           # 비즈니스 로직
│   │   └── utils/              # 유틸리티
│   ├── scripts/                # 개발/테스트 스크립트
│   └── .env                    # 환경변수
│
└── frontend/frontapp/          # React 프론트엔드
    ├── components/
    │   ├── AI/                 # KnowledgeGraph, RAGSearch 등
    │   └── Admin/              # 관리자 컴포넌트
    ├── context/                # React Context
    └── services/               # API 서비스
```

### 2.2 Backend 상세 구조
```
backend/app/
├── main.py                      # FastAPI 진입점
├── common/
│   ├── enums.py                 # SecurityLevel, SSoTLevel, ReviewStatus
│   ├── schemas.py               # Evidence, Citation, RAGResponse
│   ├── types.py                 # AuthContext, RequestScope
│   └── vector_schema.py         # 벡터 메타데이터 키
├── core/
│   ├── config.py                # Pydantic Settings (.env 로딩)
│   ├── dependencies.py          # get_current_user, get_db
│   └── gcp_clients.py           # Firestore, Drive 클라이언트
├── rag/
│   ├── orchestrator.py          # 파이프라인 오케스트레이터
│   ├── retriever.py             # 벡터 검색
│   ├── generator.py             # LLM 응답 생성
│   ├── rules/
│   │   ├── entity_types.txt     # 엔티티 타입
│   │   ├── policy_rules.v1.json # 보안 규칙
│   │   └── stopwords.txt        # 불용어
│   └── steps/                   # 15개 스텝 (아래 상세)
├── routers/
│   ├── auth.py                  # Google OAuth, JWT
│   ├── ingest.py                # 문서 수집 API
│   ├── rag_search.py            # RAG 검색 API
│   ├── graph_api.py             # 그래프 API
│   ├── tree_api.py              # 트리 API
│   └── ...                      # 기타 API
└── services/
    ├── firestore_repo.py        # 데이터 접근 레이어
    ├── graph_query_service.py   # 그래프 쿼리
    ├── ingestion_service.py     # 수집 로직
    └── ...                      # 기타 서비스
```

---

## 3. Backend 상세

### 3.1 main.py 구성
```python
# 미들웨어 순서 (중요!)
1. CORSMiddleware          # 모든 origin 허용
2. SessionMiddleware       # Google OAuth 세션
3. AuthContextMiddleware   # JWT → AuthContext 변환

# 라우터 등록
- auth.router              # /auth/*
- ingest.router            # /drive/*
- rag_search.router        # /api/search/*
- graph_api.router         # /api/graph/*
- tree_api.router          # /api/tree
- card_docs_api.router     # /api/docs/*
- ...
```

### 3.2 core/config.py 주요 설정
| 그룹 | 변수 |
|------|------|
| **GCP** | `PROJECT_ID`, `GOOGLE_APPLICATION_CREDENTIALS` |
| **OAuth** | `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `SECRET_KEY` |
| **저장소** | `FIRESTORE_DATABASE`, `GCS_BUCKET`, `GCS_PREFIX` |
| **RAG 스코프** | `TENANT_ID`, `ENGAGEMENT_ID` |
| **Vertex AI** | `VERTEX_LOCATION`, `VERTEX_MODEL_NAME`, `VERTEX_EMBED_MODEL` |
| **Vector Search** | `VECTOR_INDEX_NAME`, `VECTOR_INDEX_ENDPOINT`, `VECTOR_DEPLOYED_INDEX_ID` |
| **Document AI** | `DOC_AI_LOCATION`, `DOC_AI_PROCESSOR_ID_PDF`, `DOC_AI_PROCESSOR_ID_IMAGE` |

### 3.3 주요 API 엔드포인트

#### 인증 (`/auth/*`)
| 엔드포인트 | 메서드 | 설명 |
|------------|--------|------|
| `/auth/google` | POST | 프론트엔드 코드 교환 (메인) |
| `/users/me` | GET | 현재 사용자 프로필 |

#### 문서 수집 (`/drive/*`)
| 엔드포인트 | 메서드 | 설명 |
|------------|--------|------|
| `/drive/ingest` | POST | 단일 파일 수집 |
| `/drive/sync-folder` | POST | 폴더 전체 동기화 (백그라운드) |
| `/drive/unsync-folder` | DELETE | 동기화 중지 |
| `/drive/batch-process` | POST | 배치 AI 분석 |

#### RAG 검색 (`/api/search/*`)
| 엔드포인트 | 메서드 | 설명 |
|------------|--------|------|
| `/api/search/rag` | POST | RAG 검색 수행 |

#### 그래프 (`/api/graph/*`)
| 엔드포인트 | 메서드 | 설명 |
|------------|--------|------|
| `/api/graph/init` | GET | 초기 그래프 로드 |
| `/api/graph/expand` | GET | 노드 확장 (3-Hop) |

---

## 4. Frontend 상세

### 4.1 주요 컴포넌트
```
components/
├── AI/
│   ├── KnowledgeGraph.tsx    # D3.js 그래프 시각화
│   ├── RAGSearchPanel.tsx    # RAG 검색 UI
│   ├── DocDetailDrawer.tsx   # 문서 상세 드로어
│   └── DocTreeBrowser.tsx    # 트리 탐색기
├── DriveSyncPanel.tsx        # Drive 동기화 패널
├── SecurityTab.tsx           # 보안 대시보드
└── OmniHubTab.tsx            # 메인 탭
```

### 4.2 서비스 레이어 (`services/`)

#### aiService.ts
```typescript
AIService = {
  searchRAG(query, scope)      // POST /api/search/rag
  getGraphInit(limit, mode)    // GET /api/graph/init
  expandGraph(nodeId, type)    // GET /api/graph/expand
  getTreeStructure(path)       // GET /api/tree
  getDocCard(docId)            // GET /api/docs/{docId}
}
```

#### dataService.ts
```typescript
BackendAPI = {
  exchangeToken(code)          // POST /auth/google
  syncFolder(folderId)         // POST /drive/sync-folder
  unsyncFolder(folderId)       // DELETE /drive/unsync-folder
  fetchCurrentUser()           // GET /users/me
}
```

### 4.3 주요 타입 (types.ts)
```typescript
interface GraphNode { id, label, group, type, val }
interface GraphLink { source, target, value, rank_score }
interface GraphData { nodes: GraphNode[], links: GraphLink[] }
interface RAGResponse { answer, citations, meta }
interface DocCard { doc_id, title, card: {l1, l2, l3}, concepts }
```

---

## 5. RAG 파이프라인

### 5.1 파이프라인 아키텍처 (v2.1)
```
[Phase B - Sequential]
┌──────────────────────────────────────┐
│          1. Extract (DocAI/Excel)    │
│  ┌─────────────┐   ┌─────────────┐   │
│  │  PDF/Image  │   │   Excel     │   │  ← MIME Type 분기
│  │   (DocAI)   │   │  (Local)    │   │
│  └──────┬──────┘   └──────┬──────┘   │
│         └────────┬────────┘          │
└──────────────────┼───────────────────┘
                   ▼
          ┌─────────────┐
          │  2. Profile │  ← 메타데이터 정규화
          └──────┬──────┘
                 ▼
          ┌─────────────┐
          │ 2.5 Tree    │  ← On-the-fly Index
          └──────┬──────┘
                 ▼
          ┌─────────────┐
          │  3. Chunk   │  ← 텍스트 분할
          └──────┬──────┘
                 │
[Phase B-2 - Parallel]
┌─────────────┐ ┌─────────────┐ ┌─────────────┐
│ 4. Policy   │ │ 5. Summary  │ │ 6. Entity   │
│  (분류)      │ │  (요약)      │ │  (NER/RE)   │
└──────┬──────┘ └──────┬──────┘ └──────┬──────┘
       └───────────────┼───────────────┘
                       ▼
              ┌─────────────┐
              │  7. Merge   │  ← 아티팩트 병합
              └──────┬──────┘
                     │
    ┌────────────────┴────────────────┐
    ▼                                 ▼
[Track A: Vector]              [Track B: Graph]
┌─────────────┐                ┌─────────────┐
│  8. Embed   │                │ 8. Concepts │
└──────┬──────┘                └──────┬──────┘
       ▼                              ▼
┌─────────────┐                ┌─────────────┐
│ 9. Vector   │                │ 9. Edges    │
│   Upsert    │                │   Build     │
└──────┬──────┘                └──────┬──────┘
       ▼                              ▼
┌─────────────┐                ┌─────────────┐
│ 10. Meta    │                │ 10. Ranker  │
│   Index     │                │  (TF-IDF)   │
└─────────────┘                └──────┬──────┘
                                      ▼
                               ┌─────────────┐
                               │ 11. Serving │
                               │   Index     │
                               └─────────────┘
```

### 5.2 각 스텝 상세

| # | 스텝 | 파일 | 입력 | 출력 |
|---|------|------|------|------|
| 1 | Extract | `run_docai_extract.py`, `run_excel_extract.py` | GCS URI | `docai_results` |
| 2 | Profile | `build_profile.py` | `files` | `profiles` |
| 2.5 | Tree | `tree_indexer_service.py` | `profiles` | `tree_index` |
| 3 | Chunk | `split_and_chunk.py` | `docai_results` | `chunks` |
| 4 | Policy | `classify_doc_policy.py` | `profiles` | `policies` |
| 5 | Summary | `summarize_for_card.py` | `chunks` | `cards` |
| 6 | Entity | `extract_entities_relations.py` | `chunks` | `entities` |
| 7 | Merge | `merge_doc_artifacts.py` | 모든 아티팩트 | `doc_bundles` |
| 8a | Embed | `embed_chunks.py` | `chunks` | `embeddings` |
| 9a | Vector | `upsert_vector_index.py` | `embeddings` | Matching Engine |
| 10a | Meta | `upsert_doc_index_meta.py` | 모든 메타 | `documents` |
| 8b | Concepts | `build_concepts.py` | `entities` | `concepts` |
| 9b | Edges | `build_graph_edges.py` | `entities` | `edges_doc_concept` |
| 10b | Ranker | `edge_ranker.py` | `edges` | 점수 계산 |
| 11 | Serving | `build_graph_serving_index.py` | 엣지/개념 | `graph_serving_*` |

---

## 6. 데이터 흐름

### 6.1 문서 수집 흐름
```
[Frontend]                    [Backend]                    [GCP]
    │ POST /drive/sync-folder     │                          │
    ├─────────────────────────────►│                          │
    │                             │  Drive API (list_files)  │
    │                             ├──────────────────────────►│
    │                             │◄──────────────────────────┤
    │                             │  stream_file_to_gcs()    │
    │                             ├──────────────────────────►│ GCS
    │                             │  Firestore: files/{id}   │
    │                             ├──────────────────────────►│ Firestore
    │◄────────────────────────────┤                          │
```

### 6.2 RAG 검색 흐름
```
[Query] → [Retriever] → [Vertex AI Embedding]
                ↓
         [Matching Engine] → Top-K Chunks
                ↓
         [Generator (Gemini)] → Answer
                ↓
         [RAGResponse] → Frontend
```

### 6.3 그래프 확장 흐름
```
[노드 클릭] → /api/graph/expand?node_id=X&node_type=concept
                ↓
         [GraphQueryService.expand_neighborhood()]
                ↓
         [FirestoreRepo.get_concept_neighbors()]
                ↓
         [graph_serving_concepts/{id}]
                ↓
         {nodes: [...], links: [...]}
```

---

## 7. Firestore 컬렉션

| 컬렉션 | 문서 ID | 용도 |
|--------|---------|------|
| `users` | email | 사용자 정보 |
| `files` | fil_{driveId} | 원본 파일 메타 |
| `profiles` | doc_id | 문서 프로필 |
| `docai_results` | doc_id | OCR 결과 |
| `chunks` | doc_id | 청크 메타/GCS URI |
| `policies` | doc_id | 보안 분류 |
| `cards` | doc_id | 카드 요약 (L1/L2/L3) |
| `entities` | doc_id | 엔티티 추출 결과 |
| `embeddings` | doc_id | 임베딩 메타 |
| `documents` | doc_id | **서빙용 최종 문서** |
| `concepts` | concept_id | 정규화된 개념 |
| `edges_doc_concept` | doc__concept | 문서-개념 엣지 |
| `graph_serving_docs` | doc_id | 그래프 서빙 (문서) |
| `graph_serving_concepts` | concept_id | 그래프 서빙 (개념) |
| `tree_index` | tenant__engagement__hash | 트리 인덱스 |

---

## 8. 환경 변수

```bash
# GCP
PROJECT_ID=jnu-rise-edu-150
GCP_PROJECT_ID=jnu-rise-edu-150
GOOGLE_APPLICATION_CREDENTIALS=app/_local_secrets/service_account.json

# OAuth
GOOGLE_CLIENT_ID=xxx.apps.googleusercontent.com
GOOGLE_CLIENT_SECRET=xxx
SECRET_KEY=your-jwt-secret

# 저장소
FIRESTORE_DATABASE=(default)
GCS_BUCKET=omnihub-v1-storage-150
GCS_PREFIX=omnihub-data

# RAG 스코프
TENANT_ID=my-tenant
ENGAGEMENT_ID=eng-001

# Vertex AI
VERTEX_LOCATION=us-central1
VERTEX_MODEL_NAME=gemini-2.5-flash
VERTEX_EMBED_MODEL=text-embedding-004

# Vector Search
VECTOR_INDEX_NAME=projects/.../indexes/xxx
VECTOR_INDEX_ENDPOINT=projects/.../indexEndpoints/xxx
VECTOR_DEPLOYED_INDEX_ID=xxx

# Document AI
DOC_AI_LOCATION=us
DOC_AI_PROCESSOR_ID_PDF=xxx
DOC_AI_PROCESSOR_ID_IMAGE=xxx
```

---

## 9. 기술 스택

### Backend
| 카테고리 | 기술 |
|----------|------|
| 프레임워크 | FastAPI |
| 언어 | Python 3.11+ |
| 인증 | Google OAuth 2.0, JWT |
| 데이터베이스 | Firestore |
| 스토리지 | Google Cloud Storage |
| AI/ML | Vertex AI (Gemini, Embeddings), Document AI |
| 벡터 검색 | Vertex AI Matching Engine |
| 비동기 | asyncio, ThreadPoolExecutor |
| 배포 | Docker, Cloud Run |

### Frontend
| 카테고리 | 기술 |
|----------|------|
| 프레임워크 | React 18 |
| 언어 | TypeScript |
| 빌드 | Vite |
| 상태관리 | React Context |
| 시각화 | D3.js (force-directed graph) |
| 스타일 | CSS (Vanilla) |

### Infrastructure
| 카테고리 | 기술 |
|----------|------|
| 컴퓨팅 | Cloud Run |
| 분석 | BigQuery |
| 모니터링 | Cloud Logging |

---

> **Note**: 이 문서는 2026년 2월 8일 기준 코드 분석 결과입니다.
