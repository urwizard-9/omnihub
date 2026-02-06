from google.cloud import bigquery
from google.cloud.bigquery import SchemaField # Schema 정의용
from google.api_core.exceptions import NotFound
from app.core.config import settings
# from app.core.gcp_clients import db # [Removed] Unused dependency
import datetime
import json
import uuid

# Global Client
_bq_client = None
_checked_tables = set() # 테이블 존재 여부 캐싱

def get_bq_client():
    global _bq_client
    if not _bq_client:
        # [Modify] Use ADC (Cloud Run Standard)
        # Service Account Key File is not required in Cloud Run env.
        _bq_client = bigquery.Client(project=settings.PROJECT_ID)
    return _bq_client

# Constants
DATASET_ID = "omnihub_ai_b_dataset" # 사용자가 생성한 데이터셋 이름
LOGS_TABLE = "audit_logs_raw_changelog"
FILES_TABLE = "files_raw_changelog"

def _ensure_dataset():
    """
    데이터셋이 존재하는지 확인하고, 없으면 생성합니다.
    """
    client = get_bq_client()
    dataset_ref = client.dataset(DATASET_ID)
    
    try:
        client.get_dataset(dataset_ref)
        print(f"✅ [BigQuery] Dataset {DATASET_ID} exists.")
    except NotFound:
        print(f"⚠️ [BigQuery] Dataset {DATASET_ID} not found. Creating...")
        dataset = bigquery.Dataset(dataset_ref)
        dataset.location = "asia-northeast3" # [Locality] Match Cloud Run region
        try:
            client.create_dataset(dataset)
            print(f"✅ [BigQuery] Dataset {DATASET_ID} created.")
        except Exception as e:
            print(f"❌ [BigQuery Critical] Failed to create dataset: {e}")
            raise e

def _ensure_table(table_name: str):
    """
    테이블이 존재하는지 확인하고, 없으면 생성합니다. (Auto-Schema)
    """
    if table_name in _checked_tables:
        return

    _ensure_dataset() # [Fix] Ensure Dataset first

    client = get_bq_client()
    table_id = f"{settings.PROJECT_ID}.{DATASET_ID}.{table_name}"

    try:
        client.get_table(table_id) # 존재 확인
        _checked_tables.add(table_name)
    except NotFound:
        print(f"⚠️ [BigQuery] Table {table_name} not found. Creating...")
        
        # Schema Definition (Firebase Extension Compatible)
        schema = [
            SchemaField("timestamp", "TIMESTAMP", mode="REQUIRED"),
            SchemaField("document_id", "STRING", mode="REQUIRED"),
            SchemaField("operation", "STRING", mode="REQUIRED"),
            SchemaField("data", "STRING", mode="REQUIRED"), # JSON String
        ]
        
        table = bigquery.Table(table_id, schema=schema)
        table = client.create_table(table) 
        print(f"✅ [BigQuery] Table {table_name} created successfully.")
        _checked_tables.add(table_name)
    except Exception as e:
        print(f"❌ [BigQuery System Error] Table Check Failed: {e}")

def stream_logs_to_bigquery(log_data: dict):
    """
    logs 컬렉션의 데이터(Strict Schema: 6 fields)를 BigQuery로 스트리밍합니다.
    """
    try:
        # if not settings.PROJECT_ID: return # 로컬 테스트 등의 경우 스킵

        _ensure_table(LOGS_TABLE) # 테이블 존재 보장
        
        client = get_bq_client()
        table_ref = client.dataset(DATASET_ID).table(LOGS_TABLE)
        
        row = {
            "timestamp": datetime.datetime.utcnow().isoformat(),
            "document_id": f"log_{uuid.uuid4()}", 
            "operation": "INSERT",
            "data": json.dumps(log_data, default=str) # [Fix] Handle datetime serialization
        }
        
        errors = client.insert_rows_json(table_ref, [row])
        
        if errors:
            print(f"❌ [BigQuery Error] Log Insert Failed: {errors}")
        else:
            print(f"✅ [BigQuery] Log Streamed")
            
    except Exception as e:
        print(f"❌ [BigQuery System Error] {e}")

def stream_files_to_bigquery(file_data: dict, file_id: str):
    """
    files 컬렉션의 변경사항을 BigQuery로 스트리밍합니다.
    """
    try:
        # if not settings.PROJECT_ID: return  

        _ensure_table(FILES_TABLE) # 테이블 존재 보장
        
        client = get_bq_client()
        table_ref = client.dataset(DATASET_ID).table(FILES_TABLE)
        
        row = {
            "timestamp": datetime.datetime.utcnow().isoformat(),
            "document_id": file_id,
            "operation": "INSERT", 
            "data": json.dumps(file_data)
        }
        
        errors = client.insert_rows_json(table_ref, [row])
        
        if errors:
            print(f"❌ [BigQuery Error] File Insert Failed: {errors}")
        else:
            print(f"✅ [BigQuery] File Streamed: {file_id}")
            
    except Exception as e:
        print(f"❌ [BigQuery System Error] {e}")
