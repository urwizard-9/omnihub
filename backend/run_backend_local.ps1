
# run_backend_local.ps1
# Backend 로컬 실행 스크립트

Write-Host "🚀 Starting OmniHub Backend (Local)..."

# 1. 가상환경 활성화 (필요시 경로 수정)
# 여기서는 omnihub라는 conda env를 쓴다고 가정하거나, venv를 찾습니다.
# 만약 conda를 쓴다면 터미널에서 `conda activate omnihub`를 먼저 하라고 안내합니다.
# (스크립트 내에서 conda activate는 까다로울 수 있음)

# 2. .env 파일 확인
if (-Not (Test-Path ".env")) {
    Write-Host "⚠️ Warning: .env file not found in backend directory."
    Write-Host "Please make sure environment variables are set."
}

# 3. 서비스 계정 키 확인 (매우 중요)
$env:GOOGLE_APPLICATION_CREDENTIALS = $env:GOOGLE_APPLICATION_CREDENTIALS
if (-Not $env:GOOGLE_APPLICATION_CREDENTIALS) {
    # .env에서 읽어오기 시도 (간단한 파싱)
    if (Test-Path ".env") {
        Get-Content .env | ForEach-Object {
            if ($_ -match "^GOOGLE_APPLICATION_CREDENTIALS=(.*)") {
                $env:GOOGLE_APPLICATION_CREDENTIALS = $matches[1].Trim('"')
            }
        }
    }
}

if (-Not $env:GOOGLE_APPLICATION_CREDENTIALS) {
    Write-Host "❌ Error: GOOGLE_APPLICATION_CREDENTIALS environment variable is not set."
    Write-Host "Please set it in .env or your system environment variables."
    Write-Host "Example in .env: GOOGLE_APPLICATION_CREDENTIALS=C:/path/to/key.json"
    exit 1
}

Write-Host "🔑 Using Credentials: $env:GOOGLE_APPLICATION_CREDENTIALS"

# 4. 서버 실행
Write-Host "🔥 Running Uvicorn Server..."
# python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
