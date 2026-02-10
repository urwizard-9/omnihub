# 🚀 1,000 Documents Mass Indexing & Deployment Plan

## 1. 개요 (Overview)
로컬 환경을 **"데이터 인덱싱 머신"**으로 활용하여 대량의 문서를 원격 DB(GCS, Firestore, Vector Search)에 적재한 후, 데이터가 준비된 상태에서 가벼운 백엔드 서버를 Cloud Run에 배포합니다.

- **전략**: `Local Machine` (Heavy Processing) -> `Remote DBs` -> `Cloud Run` (Lightweight Serving)
- **예상 소요 시간**: 약 2~4시간 (문서 양 및 DocAI 속도에 따름)

---

## 2. 사전 준비 (Prerequisites)
- [ ] **문서 준비**: PDF/DOCX 파일 1,000개 준비
- [ ] **비용 확인**: Document AI 비용 (약 $1.5 / 1,000페이지) 및 Quota 확인
    - *Quota Exceeded* 에러 방지를 위해 배치 처리 권장
- [ ] **GCP 권한**: 로컬 터미널에 `gcloud auth login` 및 `application_default_credentials` 설정 완료 상태

---

## 3. 실행 단계 (Execution Steps)

### Step 1: 환경 격리 및 초기화 (Clean & Isolate)
가장 확실하고 빠른 초기화 방법은 **새로운 Tenant ID**를 부여하는 것입니다. 기존 데이터를 지우느라 시간을 쓸 필요가 없습니다.

1.  **.env 설정 변경**:
    ```bash
    # PROD용 새로운 테넌트 ID 발급 (배포 환경변수로 주입)
    TENANT_ID="prod_v1_20240210"
    ```
2.  (선택) Firestore/GCS 초기화:
    - `python scripts/dev/clean_db.py` (메타데이터 삭제 - 선택사항)
    - `python scripts/dev/clean_gcs.py` (임시 파일 삭제 - 선택사항)
    - *Vector Search Index는 Tenant ID 필터링으로 인해 초기화 불필요.*

---

### Step 2: 대량 인덱싱 (Mass Indexing) - **Local 실행**
로컬 PC의 컴퓨팅 파워를 사용하여 1,000개 문서를 처리합니다.

1.  **문서 배치**:
    - `backend/data/input/` 폴더에 문서 1,000개 복사.
2.  **파이프라인 실행**:
    ```bash
    # 전체 파이프라인 실행 (DocAI -> Chunk -> Embed -> Upsert)
    # 배치 사이즈를 적절히 조절하여 실행 (예: 50개씩)
    python scripts/pipeline_runner.py --batch_size 50
    ```
    - *Tip*: 1,000개를 한 번에 돌리기보다 50~100개씩 끊어서 돌리는 것을 권장합니다 (에러 발생 시 재시도 용이, Quota 관리).
3.  **검증**:
    - Firestore에 1,000개 문서 생성 확인.
    - Vector Search Index에 데이터 포인트(Chunk 수) 증가 확인.

---

### Step 3: 백엔드 배포 (Cloud Run Deploy)
데이터가 다 들어갔으므로, 이제 서버를 띄웁니다.

1.  **Dockerfile 확인**:
    - `backend/Dockerfile`이 최신 코드를 포함하는지 확인.
2.  **배포 명령 실행**:
    ```powershell
    gcloud run deploy omnihub-backend-v1 `
      --source . `
      --region us-central1 `
      --allow-unauthenticated `
      --set-env-vars "PROJECT_ID=jnu-rise-edu-150,TENANT_ID=prod_v1_20240210" `
      --set-env-vars "RETRIEVER_TOPK_MULT=15,PER_DOC_CHUNK_CAP=5" `
      --set-env-vars "MAX_CONTEXT=15,MAX_CHUNK_LENGTH=2000"
    ```
    - *주의*: `.env`에 있는 핵심 변수들(`RETRIEVER_TOPK_MULT=15` 등)을 `--set-env-vars`로 모두 넘겨주거나, `env_vars.yaml` 파일을 사용하여 적용해야 합니다.

---

## 4. 모니터링 및 리스크 관리
| 리스크 요소 | 대응 방안 |
|------------|----------|
| **DocAI 쿼터 초과** | 파이프라인 스크립트에 `time.sleep()` 추가하거나 배치 사이즈 축소 |
| **인덱싱 중간 실패** | `pipeline_runner.py`에 '이미 처리된 파일 건너뛰기' 로직 확인 |
| **비용 급증** | Vertex AI Vector Search는 시간당 과금되므로, 사용 안 할 땐 `Undeploy` 고려 (단, 재배포 30분 소요) |

## 5. 최종 점검 (Validation)
배포 완료 후:
1.  Cloud Run URL의 `/health` 엔드포인트 호출.
2.  실제 RAG 질문 던져서 **1,000개 문서 중 해당되는 내용**이 잘 나오는지 확인.
