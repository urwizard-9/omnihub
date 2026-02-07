# OmniHub 프로젝트 아키텍처 분석 문서

> **작성일**: 2026년 2월
> **브랜치**: `front-exp-test-1` (기반: `feature/backend`)

---

## 📋 목차

1. [프로젝트 개요](#1-프로젝트-개요)
2. [폴더 구조 분석](#2-폴더-구조-분석)
3. [Backend 상세 분석](#3-backend-상세-분석)
4. [Frontend 상세 분석](#4-frontend-상세-분석)
5. [데이터 흐름 (Data Flow)](#5-데이터-흐름-data-flow)
6. [Firestore 컬렉션 맵](#6-firestore-컬렉션-맵)
7. [환경 변수 목록](#7-환경-변수-목록)
8. [기술 스택 요약](#8-기술-스택-요약)

---

## 1. 프로젝트 개요

**OmniHub**는 Google Drive 기반의 문서 관리 및 RAG(Retrieval-Augmented Generation) 검색 시스템입니다.

### 핵심 기능

| 기능 | 설명 |
|------|------|
| **문서 수집 (Ingestion)** | Google Drive에서 파일을 GCS로 스트리밍하고 메타데이터 저장 |
| **Document AI 처리** | PDF/이미지에서 텍스트 추출 (OCR) |
| **RAG 파이프라인** | 문서 청킹, 임베딩, 벡터 DB 저장, 시맨틱 검색 |
| **Knowledge Graph** | 문서-개념 간 관계 그래프 구축 및 시각화 |
| **보안 분류** | 문서별 Security Level, SSOT Level 자동 분류 |
| **실시간 동기화** | Google Drive Webhook을 통한 변경 감지 |

---

## 2. 폴더 구조 분석

### 2.1 전체 프로젝트 구조

```
omnihub/
├── backend/                    # FastAPI 백엔드 서버
│   ├── app/                    # 메인 애플리케이션 코드
│   │   ├── common/             # 공통 스키마 및 유틸리티
│   │   ├── core/               # 핵심 설정 및 GCP 클라이언트
│   │   ├── models/             # Pydantic 데이터 모델
│   │   ├── rag/                # RAG 파이프라인 (오케스트레이터 및 스텝들)
│   │   ├── routers/            # FastAPI API 엔드포인트
│   │   └── services/           # 비즈니스 로직 서비스
│   ├── scripts/                # 개발/테스트 스크립트
│   ├── static/                 # 정적 파일
│   └── ref/                    # 레퍼런스 코드
│
├── frontend/                   # React 프론트엔드
│   └── frontapp/
│       ├── components/         # React UI 컴포넌트
│       ├── context/            # React Context Providers
│       ├── services/           # API 호출 서비스
│       └── public/             # 정적 자산
│
└── README.md
```

### 2.2 Backend 디렉토리 상세 구조

```
backend/
├── app/
│   ├── __init__.py
│   ├── main.py                         # FastAPI 앱 진입점
│   │
│   ├── common/                          # 공통 모듈
│   │   ├── drive_watch.py              # Drive Webhook 설정
│   │   ├── enums.py                    # SecurityLevel, SSoTLevel, ReviewStatus 열거형
│   │   ├── schemas.py                  # Evidence, Citation, RAGResponse 스키마
│   │   ├── types.py                    # AuthContext, RequestScope 타입
│   │   └── vector_schema.py            # 벡터 검색 메타데이터 키 정의
│   │
│   ├── core/                            # 핵심 설정
│   │   ├── config.py                   # Pydantic Settings (환경변수)
│   │   ├── dependencies.py             # FastAPI 의존성 주입
│   │   ├── gcp_clients.py              # Firestore, Drive API 클라이언트
│   │   └── logger.py                   # 구조화된 JSON 로깅
│   │
│   ├── models/                          # 데이터 모델
│   │   ├── ai_insight.py               # AI 분석 결과 스키마
│   │   ├── file.py                     # 파일 메타데이터 스키마
│   │   ├── log.py                      # 감사 로그 스키마
│   │   ├── user.py                     # 사용자 정보 스키마
│   │   └── watch.py                    # Drive Webhook 채널 스키마
│   │
│   ├── rag/                             # RAG 파이프라인
│   │   ├── doc_workflow_rules.py       # 문서 상태별 워크플로우 규칙
│   │   ├── generator.py                # LLM 응답 생성기 (Vertex AI)
│   │   ├── orchestrator.py             # 파이프라인 오케스트레이터
│   │   ├── retriever.py                # 벡터 검색 리트리버
│   │   │
│   │   ├── rules/                       # 규칙 파일
│   │   │   ├── entity_types.txt        # 엔티티 타입 정의
│   │   │   └── policy_rules.v1.json    # 보안 분류 규칙
│   │   │
│   │   └── steps/                       # 파이프라인 개별 스텝
│   │       ├── run_docai_extract.py    # Document AI OCR 추출
│   │       ├── build_profile.py        # 문서 프로필 생성
│   │       ├── split_and_chunk.py      # 텍스트 청크 분할
│   │       ├── classify_doc_policy.py  # 보안/SSOT 분류
│   │       ├── summarize_for_card.py   # 카드 요약 생성
│   │       ├── extract_entities_relations.py  # 엔티티/관계 추출
│   │       ├── merge_doc_artifacts.py  # 아티팩트 병합
│   │       ├── embed_chunks.py         # 청크 임베딩 생성
│   │       ├── upsert_vector_index.py  # 벡터 인덱스 업서트
│   │       ├── upsert_doc_index_meta.py  # 문서 메타 인덱싱
│   │       ├── build_concepts.py       # 개념 집계
│   │       ├── build_graph_edges.py    # 그래프 엣지 생성
│   │       ├── edge_ranker.py          # 엣지 랭킹
│   │       └── build_graph_serving_index.py  # 서빙 인덱스 구축
│   │
│   ├── routers/                         # API 라우터
│   │   ├── auth.py                     # 인증 (Google OAuth, JWT)
│   │   ├── auth_context.py             # 인증 컨텍스트 미들웨어
│   │   ├── ingest.py                   # 문서 수집 API
│   │   ├── drive_webhook.py            # Drive 웹훅 핸들러
│   │   ├── rag_search.py               # RAG 검색 API
│   │   ├── files.py                    # 파일 관리 API
│   │   ├── graph_api.py                # 그래프 API
│   │   ├── tree_api.py                 # 트리 구조 API
│   │   ├── card_docs_api.py            # 문서 카드 API
│   │   ├── docs_status_api.py          # 문서 상태 API
│   │   ├── admin.py                    # 관리자 API
│   │   ├── download_api.py             # 다운로드 API
│   │   └── rate_limit_guard.py         # Rate Limiting
│   │
│   └── services/                        # 비즈니스 서비스
│       ├── drive_service.py            # Google Drive 연동
│       ├── firestore_repo.py           # Firestore 레포지토리
│       ├── ingestion_service.py        # 문서 수집 로직
│       ├── log_service.py              # 로깅 서비스
│       ├── bq_service.py               # BigQuery 서비스
│       ├── graph_query_service.py      # 그래프 쿼리
│       ├── tree_indexer_service.py     # 트리 인덱싱
│       ├── permission_service.py       # 권한 관리
│       ├── signed_url_service.py       # Signed URL 생성
│       ├── metadata_extractor.py       # 메타데이터 추출
│       └── ai_a/                       # AI 분석 서비스
│           └── analysis_service.py
│
├── scripts/                             # 유틸리티 스크립트
│   ├── dev/                            # 개발용
│   ├── test/                           # 테스트용
│   ├── refactor_db_import.py
│   ├── test_rag_pipeline.py
│   └── verify_backend.py
│
├── Dockerfile                           # 컨테이너 빌드
├── requirements.txt                     # Python 의존성
├── .env.example                         # 환경변수 예시
└── .gitignore
```

---

## 3. Backend 상세 분석

### 3.1 Core 모듈

#### `main.py` - 애플리케이션 진입점
```python
# 주요 기능:
# - FastAPI 앱 인스턴스 생성
# - CORS 미들웨어 설정 (모든 origin 허용)
# - SessionMiddleware (Google OAuth용)
# - AuthContextMiddleware (인증 컨텍스트 주입)
# - 모든 라우터 등록
# - /static 정적 파일 서빙
```

#### `core/config.py` - 환경 설정
| 설정 그룹 | 주요 변수 |
|-----------|-----------|
| **GCP 기본** | `PROJECT_ID`, `LOCATION`, `GOOGLE_APPLICATION_CREDENTIALS` |
| **OAuth** | `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `SECRET_KEY` |
| **Document AI** | `DOCAI_LOCATION`, `DOCAI_PROCESSOR_ID_PDF`, `DOCAI_PROCESSOR_ID_IMAGE` |
| **저장소** | `FIRESTORE_DATABASE`, `GCS_BUCKET`, `GCS_PREFIX` |
| **RAG 스코프** | `TENANT_ID`, `ENGAGEMENT_ID` |
| **Vertex AI** | `VERTEX_LOCATION`, `VERTEX_MODEL_NAME`, `VERTEX_EMBED_MODEL` |
| **벡터 검색** | `VECTOR_INDEX_NAME`, `VECTOR_INDEX_ENDPOINT`, `VECTOR_DEPLOYED_INDEX_ID` |

#### `core/dependencies.py` - 의존성 주입
- `get_db()`: Firestore 클라이언트 반환
- `get_current_user()`: JWT 토큰 검증 및 사용자 정보 반환
  - **Bypass Mode**: `BYPASS_TOKEN="DEBUG_LOCAL"` 시 더미 사용자 반환

#### `core/gcp_clients.py` - GCP 클라이언트
- Firebase Admin SDK 초기화
- Firestore 클라이언트 (`get_firestore_client()`)
- Google Drive API 클라이언트 (`get_drive_service()`)

---

### 3.2 RAG 파이프라인 상세

#### 파이프라인 실행 흐름 (Orchestrator)

```
┌─────────────────────────────────────────────────────────────────────┐
│                      RAG Pipeline Orchestrator                      │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  [Phase A: 수집 & 프로필]                                            │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │ 1. run_docai_extract  →  Document AI로 OCR/텍스트 추출      │   │
│  │ 2. build_profile      →  프로필 문서 생성/업데이트           │   │
│  │ 3. split_and_chunk    →  텍스트를 청크로 분할               │   │
│  └──────────────────────────────────────────────────────────────┘   │
│                                ↓                                    │
│  [Phase B: 분석 (병렬 실행)] ─────────────────────────────────────    │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────────────┐   │
│  │ classify_    │  │ summarize_   │  │ extract_entities_        │   │
│  │ doc_policy   │  │ for_card     │  │ relations                │   │
│  │ (보안분류)    │  │ (요약생성)    │  │ (엔티티추출)              │   │
│  └──────────────┘  └──────────────┘  └──────────────────────────┘   │
│                                ↓                                    │
│  [Phase C: 병합 & 인덱싱]                                            │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │ 4. merge_doc_artifacts   →  분석 결과 통합                   │   │
│  │ 5. embed_chunks          →  청크 임베딩 생성                 │   │
│  │ 6. upsert_vector_index   →  벡터 DB 업서트                   │   │
│  │ 7. upsert_doc_index_meta →  문서 메타 인덱싱                 │   │
│  └──────────────────────────────────────────────────────────────┘   │
│                                ↓                                    │
│  [Phase D: 그래프 구축]                                              │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │ 8. build_concepts        →  개념 집계 (Incremental)          │   │
│  │ 9. build_graph_edges     →  문서-개념 엣지 생성              │   │
│  │ 10. edge_ranker          →  엣지 점수 계산                   │   │
│  │ 11. build_graph_serving  →  서빙 인덱스 구축                 │   │
│  └──────────────────────────────────────────────────────────────┘   │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

#### 각 스텝 상세 설명

| 스텝 | 파일명 | 입력 | 출력 | 설명 |
|------|--------|------|------|------|
| **DocAI Extract** | `run_docai_extract.py` | GCS URI, MIME type | Firestore(`docai_results`), GCS | Document AI로 OCR 수행, 텍스트/레이아웃 추출 |
| **Build Profile** | `build_profile.py` | `files/{doc_id}` | Firestore(`profiles`) | 메타데이터 통합, 변경 감지, 재처리 플래그 설정 |
| **Split & Chunk** | `split_and_chunk.py` | `docai_results` | Firestore(`chunks`), GCS | 텍스트를 512토큰 청크로 분할 (128토큰 오버랩) |
| **Classify Policy** | `classify_doc_policy.py` | `profiles` | Firestore(`policies`, `documents`) | 폴더/키워드 규칙으로 보안레벨 분류 |
| **Summarize Card** | `summarize_for_card.py` | `chunks` | Firestore(`cards`) | LLM으로 3단계 요약 생성 (L1/L2/L3) |
| **Extract Entities** | `extract_entities_relations.py` | `chunks` | Firestore(`entities`), GCS | LLM으로 엔티티/관계 추출 (병렬 5스레드) |
| **Merge Artifacts** | `merge_doc_artifacts.py` | 모든 아티팩트 | Firestore(`doc_bundles`), GCS | 분석 결과를 번들로 통합 |
| **Embed Chunks** | `embed_chunks.py` | `chunks` | Firestore(`embeddings`), GCS | Vertex AI로 텍스트 임베딩 생성 |
| **Upsert Vector** | `upsert_vector_index.py` | `embeddings` | Matching Engine Index | 벡터 데이터포인트 업서트 |
| **Upsert Doc Meta** | `upsert_doc_index_meta.py` | 모든 메타 | Firestore(`documents`) | 서빙용 문서 메타 최종 저장 |
| **Build Concepts** | `build_concepts.py` | `entities` | Firestore(`concepts`, `concept_maps`) | 엔티티 → 정규화된 개념으로 집계 |
| **Build Graph Edges** | `build_graph_edges.py` | `entities`, `concept_map` | Firestore(`edges_doc_concept`) | 문서-개념 연결 엣지 생성 |
| **Edge Ranker** | `edge_ranker.py` | `edges_doc_concept` | 업데이트된 `edges`, `documents` | TF-IDF 유사 점수로 엣지 랭킹 |
| **Graph Serving** | `build_graph_serving_index.py` | 엣지, 개념, 문서 | `graph_serving_docs`, `graph_serving_concepts` | 그래프 조회용 인덱스 구축 |

---

### 3.3 API 라우터 상세

#### 인증 (`routers/auth.py`)
| 엔드포인트 | 메서드 | 설명 |
|------------|--------|------|
| `/auth/login` | GET | (테스트용) 서버 리다이렉트 OAuth |
| `/auth/callback` | GET | OAuth 콜백 처리 |
| `/auth/google` | POST | 프론트엔드 코드 교환 (메인 프로덕션) |
| `/users/me` | GET | 현재 사용자 프로필 반환 |

#### 문서 수집 (`routers/ingest.py`)
| 엔드포인트 | 메서드 | 설명 |
|------------|--------|------|
| `/drive/ingest` | POST | 단일 파일 수집 |
| `/drive/sync-folder` | POST | 폴더 전체 동기화 (백그라운드) |
| `/drive/unsync-folder` | DELETE | 동기화 중지 |
| `/drive/status` | GET | 동기화 상태 확인 |
| `/drive/batch-process` | POST | 배치 AI 분석 요청 |

#### RAG 검색 (`routers/rag_search.py`)
| 엔드포인트 | 메서드 | 설명 |
|------------|--------|------|
| `/api/search/rag` | POST | RAG 검색 수행 |

**요청 본문:**
```json
{
  "query": "검색 질문",
  "scope": {
    "doc_ids": ["doc1", "doc2"],
    "folder_path": "/projects/"
  },
  "top_k": 8
}
```

**응답:**
```json
{
  "answer": "LLM 생성 답변",
  "citations": [
    {"idx": 1, "doc_id": "xyz", "title": "문서제목", "snippet": "..."}
  ],
  "meta": {"model_version": "gemini-2.0-flash-exp", "latency_ms": 1234}
}
```

---

### 3.4 서비스 레이어 상세

#### `drive_service.py` - Google Drive 연동
| 함수 | 설명 |
|------|------|
| `get_user_drive_service()` | 사용자 토큰으로 Drive API 클라이언트 생성 |
| `stream_file_to_gcs()` | Drive → GCS 스트리밍 전송 |
| `register_user_watch()` | Drive Webhook 채널 등록 |
| `resolve_full_path()` | 파일의 전체 경로 역추적 |
| `list_files_in_folder_recursive()` | 폴더 재귀 탐색 |

#### `firestore_repo.py` - 데이터 접근 레이어
| 메서드 | 설명 |
|--------|------|
| `get_document()` | 문서 조회 (Fallback 키 지원) |
| `list_documents()` | 문서 목록 조회 (페이지네이션) |
| `update_doc_status()` | 문서 상태 업데이트 (워크플로우 규칙 적용) |
| `get_graph_init()` | 초기 그래프 데이터 로드 |
| `get_doc_neighbors()` | 문서의 이웃 개념 조회 |
| `get_tree_children()` | 트리 구조 자식 노드 조회 |

#### `ingestion_service.py` - 문서 수집 핵심 로직
```python
def process_and_catalog_file(user, file_id, virtual_path, drive_meta):
    """
    1. Delta Sync Check: modifiedTime 비교로 변경 여부 확인
    2. Stream to GCS: Drive → GCS 스트리밍
    3. Stamp Metadata: Firestore에 메타데이터 저장
    4. Stream to BigQuery: BQ에 메타 기록
    5. Log Action: 감사 로그 기록
    """
```

---

## 4. Frontend 상세 분석

### 4.1 디렉토리 구조

```
frontend/frontapp/
├── index.html                    # HTML 진입점
├── index.tsx                     # React 진입점
├── App.tsx                       # 메인 앱 컴포넌트
├── types.ts                      # TypeScript 타입 정의
├── constants.ts                  # 상수 정의
├── vite.config.ts               # Vite 설정
├── package.json                  # 의존성
│
├── components/                   # UI 컴포넌트
│   ├── OmniHubTab.tsx           # 메인 허브 탭
│   ├── SecurityTab.tsx          # 보안 대시보드
│   ├── GraphVisualizer.tsx      # D3.js 그래프 시각화
│   ├── DocDetailDrawer.tsx      # 문서 상세 드로어
│   ├── DriveSyncPanel.tsx       # Drive 동기화 패널
│   ├── MonitoredFolderList.tsx  # 모니터링 폴더 목록
│   ├── SyncQueuePanel.tsx       # 동기화 큐 상태
│   ├── EventLogPanel.tsx        # 이벤트 로그
│   ├── AdminUserManagement.tsx  # 사용자 관리 (관리자)
│   ├── ErrorBoundary.tsx        # 에러 경계
│   ├── Admin/                   # 관리자 전용 컴포넌트
│   └── AI/                      # AI 관련 컴포넌트
│
├── context/                      # React Context
│   ├── OmniHubContext.tsx       # 전역 상태 관리
│   └── ToastContext.tsx         # 토스트 알림
│
└── services/                     # API 서비스
    ├── aiService.ts             # AI/RAG API 호출
    └── dataService.ts           # 데이터/인증 API 호출
```

### 4.2 주요 타입 정의 (`types.ts`)

```typescript
// 사용자
interface User {
  email: string;
  displayName: string;
  photoUrl?: string;
  department?: string;
  role: string;
}

// 문서 레코드 (UI용)
interface DocRecord {
  id: string;
  name: string;
  driveUrl: string;
  folderPath: string;      // 가상 경로
  actualPath: string;      // 실제 경로
  tags: string[];
  security: SecurityLevel;
  aiSummary3: string[];    // 3줄 요약
  status: 'idle' | 'pending' | 'approved' | 'rejected';
}

// RAG 응답
interface RAGResponse {
  answer: string;
  citations: Citation[];
  meta?: any;
  follow_up?: string[];
}

// 그래프 데이터
interface GraphData {
  nodes: GraphNode[];      // {id, label, group}
  links: GraphLink[];      // {source, target, value}
}
```

### 4.3 서비스 레이어

#### `aiService.ts` - AI API 호출
```typescript
AIService = {
  searchRAG(query, scope),     // POST /api/search/rag
  getGraphInit(limit),         // GET /api/graph/init
  expandGraph(nodeId, type),   // GET /api/graph/expand
  getTreeStructure(path),      // GET /api/tree
  getDocCard(docId)            // GET /api/docs/{docId}
}
```

#### `dataService.ts` - 데이터/인증 API
```typescript
BackendAPI = {
  exchangeToken(googleCode),   // POST /auth/google
  getDriveProxy(folderId),     // GET /drive/proxy
  syncFolder(folderId),        // POST /drive/sync-folder
  unsyncFolder(folderId),      // DELETE /drive/unsync-folder
  getSyncStatus(folderId),     // GET /drive/status
  fetchCurrentUser(),          // GET /users/me
  getUsers(),                  // GET /admin/users
  updateUser(email, updates),  // PUT /admin/users/{email}
  updateDocumentStatus(docId, status)  // PUT /api/docs/{docId}/status
}
```

---

## 5. 데이터 흐름 (Data Flow)

### 5.1 문서 수집 흐름

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         Document Ingestion Flow                              │
└─────────────────────────────────────────────────────────────────────────────┘

[Frontend]                        [Backend]                      [GCP Services]
    │                                 │                               │
    │  1. 폴더 동기화 요청            │                               │
    ├────────────────────────────────►│                               │
    │  POST /drive/sync-folder        │                               │
    │                                 │                               │
    │  2. 즉시 응답 (Background)      │                               │
    │◄────────────────────────────────┤                               │
    │                                 │                               │
    │                                 │  3. Drive API 호출            │
    │                                 ├──────────────────────────────►│
    │                                 │  list_files_recursive()       │ Google
    │                                 │◄──────────────────────────────┤ Drive
    │                                 │                               │
    │                                 │  4. 파일 스트리밍             │
    │                                 ├──────────────────────────────►│
    │                                 │  stream_file_to_gcs()         │ GCS
    │                                 │◄──────────────────────────────┤
    │                                 │                               │
    │                                 │  5. 메타데이터 저장           │
    │                                 ├──────────────────────────────►│
    │                                 │  Firestore: files/{doc_id}    │ Firestore
    │                                 │◄──────────────────────────────┤
    │                                 │                               │
    │  6. 상태 폴링                   │                               │
    ├────────────────────────────────►│                               │
    │  GET /drive/status/{folderId}   │                               │
    │                                 │                               │
    │  7. 완료 알림                   │                               │
    │◄────────────────────────────────┤                               │
```

### 5.2 RAG 파이프라인 데이터 흐름

```
┌───────────────────────────────────────────────────────────────────────────────┐
│                          RAG Pipeline Data Flow                               │
└───────────────────────────────────────────────────────────────────────────────┘

[GCS]              [Firestore]              [Vertex AI]       [Matching Engine]
  │                    │                        │                    │
  │ raw_file.pdf       │                        │                    │
  ├───────────────────►│                        │                    │
  │                    │  files/{doc_id}        │                    │
  │                    ├───────────────────────►│                    │
  │                    │                 Document AI                 │
  │                    │◄───────────────────────┤                    │
  │ docai_output/      │  docai_results/        │                    │
  │◄───────────────────┤                        │                    │
  │                    │                        │                    │
  │                    │  profiles/{doc_id}     │                    │
  │                    │  chunks/{doc_id}       │                    │
  │ chunks.json        │                        │                    │
  │◄───────────────────┤                        │                    │
  │                    │                        │                    │
  │                    │  policies/{doc_id}     │                    │
  │                    │  cards/{doc_id}        │  Gemini LLM       │
  │                    │  entities/{doc_id}     │◄──────────────────│
  │                    │                        │                    │
  │                    │  embeddings/{doc_id}   │  Embedding Model  │
  │ embeddings.json    │◄───────────────────────┤                    │
  │◄───────────────────┤                        │                    │
  │                    │                        │                    │
  │                    │                        │   Upsert Vectors  │
  │                    │                        ├───────────────────►│
  │                    │  vector_upserts/       │                    │
  │                    │                        │                    │
  │                    │  concepts/{id}         │                    │
  │                    │  edges_doc_concept/    │                    │
  │                    │  graph_serving_docs/   │                    │
  │                    │  documents/{doc_id}    │    [FINAL]        │
```

### 5.3 RAG 검색 흐름

```
┌───────────────────────────────────────────────────────────────────────────────┐
│                            RAG Search Flow                                    │
└───────────────────────────────────────────────────────────────────────────────┘

[User Query]
     │
     ▼
┌─────────────┐      ┌─────────────────┐      ┌────────────────────┐
│  Frontend   │──────│  /api/search/rag │──────│    Retriever       │
│  (React)    │      │  (FastAPI)       │      │ (Vector Search)    │
└─────────────┘      └─────────────────┘      └────────────────────┘
                            │                         │
                            │                         ▼
                            │                 ┌────────────────────┐
                            │                 │  Vertex AI         │
                            │                 │  Embedding Model   │
                            │                 │  query → vector    │
                            │                 └────────────────────┘
                            │                         │
                            │                         ▼
                            │                 ┌────────────────────┐
                            │                 │  Matching Engine   │
                            │                 │  Vector Search     │
                            │                 │  (Top-K neighbors) │
                            │                 └────────────────────┘
                            │                         │
                            │                         ▼
                            │                 ┌────────────────────┐
                            │                 │  Firestore         │
                            │                 │  documents/chunks  │
                            │                 │  (메타데이터 조회) │
                            │                 └────────────────────┘
                            │                         │
                            ▼                         │
                     ┌─────────────────┐              │
                     │    Generator    │◄─────────────┘
                     │  (Gemini LLM)   │   Context + Query
                     │                 │
                     │  "Based on the  │
                     │   context..."   │
                     └─────────────────┘
                            │
                            ▼
                     ┌─────────────────┐
                     │   RAGResponse   │
                     │ {answer, cites} │
                     └─────────────────┘
```

---

## 6. Firestore 컬렉션 맵

| 컬렉션 | 문서 ID | 용도 | 주요 필드 |
|--------|---------|------|-----------|
| `users` | email | 사용자 정보 | userId, role, department, googleAccessToken |
| `files` | fil_{driveId} | 원본 파일 메타 | gcsUri, mimeType, fullPath, status |
| `profiles` | doc_id | 문서 프로필 (변경감지) | doc_content_hash, process_flags, active |
| `docai_results` | doc_id | Document AI 결과 | text, layout, pages |
| `chunks` | doc_id | 청크 메타 | gcs_chunks_uri, chunk_count |
| `policies` | doc_id | 보안 분류 결과 | security_level, ssot_level, matched_rules |
| `cards` | doc_id | 카드 요약 | card.l1/l2/l3, card_evidence |
| `entities` | doc_id | 엔티티 추출 결과 | gcs_entities_uri, entity_count |
| `embeddings` | doc_id | 임베딩 메타 | gcs_embeddings_uri, model_version |
| `vector_upserts` | doc_id | 벡터 업서트 기록 | upserted_count, index_name |
| `documents` | doc_id | **서빙용 최종 문서** | 모든 분석 결과 통합 |
| `concepts` | concept_id | 정규화된 개념 | canonical_name, type, doc_frequency |
| `concept_maps` | tenant__engagement | 개념 매핑 | gcs_uri (alias → concept_id) |
| `edges_doc_concept` | doc__concept__edge | 문서-개념 엣지 | rank_score, mentions_count |
| `graph_serving_docs` | doc_id | 그래프 서빙 (문서) | top_concepts |
| `graph_serving_concepts` | concept_id | 그래프 서빙 (개념) | top_docs |
| `tree_index` | tenant__engagement__hash | 트리 구조 인덱스 | children_folders, children_docs |
| `doc_bundles` | doc_id | 아티팩트 번들 | gcs_bundle_uri |
| `watch_channels` | channel_id | Drive Webhook 채널 | user_email, expiration |
| `folders` | folder_id | 폴더 상태 | sync_status |
| `logs` | auto-gen | 감사 로그 | actionType, userId, fileId |

---

## 7. 환경 변수 목록

```bash
# === GCP 기본 ===
PROJECT_ID=your-gcp-project
LOCATION=asia-northeast3
GOOGLE_APPLICATION_CREDENTIALS=/path/to/service-account.json

# === OAuth ===
GOOGLE_CLIENT_ID=xxx.apps.googleusercontent.com
GOOGLE_CLIENT_SECRET=xxx
SECRET_KEY=your-jwt-secret
ALGORITHM=HS256
SUPER_ADMIN_EMAIL=admin@example.com

# === Document AI ===
DOCAI_LOCATION=us
DOCAI_PROCESSOR_ID_PDF=abc123
DOCAI_PROCESSOR_ID_IMAGE=def456

# === 저장소 ===
FIRESTORE_DATABASE=(default)
GCS_BUCKET=your-bucket-name
GCS_PREFIX=omnihub

# === RAG 스코프 ===
TENANT_ID=default
ENGAGEMENT_ID=default

# === Vertex AI ===
VERTEX_LOCATION=us-central1
VERTEX_MODEL_NAME=gemini-2.0-flash-exp
VERTEX_EMBED_MODEL=text-embedding-004

# === 벡터 검색 ===
VECTOR_INDEX_NAME=projects/.../indexes/xxx
VECTOR_INDEX_ENDPOINT=projects/.../indexEndpoints/xxx
VECTOR_DEPLOYED_INDEX_ID=deployed_index_id
VECTOR_UPSERT_BATCH_SIZE=50

# === 파이프라인 설정 ===
CHUNK_SIZE_HINT=512
CHUNK_OVERLAP_HINT=128
PIPELINE_VERSION=v0.1
POLICY_RULE_VERSION=v1
DOC_INDEX_VERSION=v1
TOP_CONCEPTS_CAP=50
PER_DOC_CAP=50
PER_NODE_CAP=50

# === 개발/테스트 ===
AUTH_MODE=bypass  # bypass, jwt, header
BYPASS_TOKEN=DEBUG_LOCAL
```

---

## 8. 기술 스택 요약

### Backend
| 카테고리 | 기술 |
|----------|------|
| **프레임워크** | FastAPI |
| **언어** | Python 3.11+ |
| **인증** | Google OAuth 2.0, JWT (python-jose) |
| **데이터베이스** | Firestore |
| **스토리지** | Google Cloud Storage |
| **AI/ML** | Vertex AI (Gemini, Embeddings), Document AI |
| **벡터 검색** | Vertex AI Matching Engine |
| **비동기** | asyncio, ThreadPoolExecutor |
| **컨테이너** | Docker, Cloud Run |

### Frontend
| 카테고리 | 기술 |
|----------|------|
| **프레임워크** | React 18 |
| **언어** | TypeScript |
| **빌드** | Vite |
| **상태관리** | React Context |
| **시각화** | D3.js (그래프) |
| **스타일링** | CSS (Vanilla) |
| **API 호출** | Fetch API |

### Infrastructure
| 카테고리 | 기술 |
|----------|------|
| **컴퓨팅** | Cloud Run |
| **CI/CD** | Cloud Build (예정) |
| **분석** | BigQuery |
| **모니터링** | Cloud Logging |

---

## 🔗 관련 문서

- [Google Cloud Vertex AI Documentation](https://cloud.google.com/vertex-ai/docs)
- [Firestore Documentation](https://cloud.google.com/firestore/docs)
- [FastAPI Documentation](https://fastapi.tiangolo.com/)

---

> **Note**: 이 문서는 코드 분석을 기반으로 자동 생성되었습니다. 실제 구현과 차이가 있을 수 있습니다.
