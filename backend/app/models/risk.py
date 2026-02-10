from pydantic import BaseModel, Field
from typing import Optional, Dict
from datetime import datetime

class RiskMetadata(BaseModel):
    userDownloads5m: Optional[int] = Field(None, description="최근 5분간 다운로드 횟수")
    zPos: Optional[float] = Field(None, description="Z-Score 위치")

class RiskGcsInfo(BaseModel):
    bucket: Optional[str] = None
    name: Optional[str] = None
    generation: Optional[str] = None

class RiskData(BaseModel):
    riskScore: float = Field(..., description="현재 리스크 점수")
    defconMode: str = Field(..., description="대응 단계 (예: alert, safe)")
    eventType: str = Field(..., description="감지된 이벤트 종류")
    eventRisk: float = Field(..., description="이번 사건으로 추가된 리스크 점수")
    
    lastEventAt: datetime = Field(..., description="마지막 이벤트 발생 시각")
    updatedAt: Optional[datetime] = Field(None, description="문서 갱신 시각")
    userId: str = Field(..., description="사용자 ID")
    
    traceId: Optional[str] = Field(None, description="추적 ID")
    stateChanged: bool = Field(False, description="상태 변경 여부")

    # Autoencoder Anomaly Metrics
    reconError: Optional[float] = Field(None, description="재구성 오차")
    trainMean: Optional[float] = Field(None, description="정상 데이터 평균 오차")
    trainStd: Optional[float] = Field(None, description="정상 데이터 표준 편차")
    p95Threshold: Optional[float] = Field(None, description="이상 탐지 임계값 (P95)")

    metadata: Optional[RiskMetadata] = None
    gcs: Optional[RiskGcsInfo] = None
