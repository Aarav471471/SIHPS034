# Start the MetriX API in development mode (SQLite + in-process workers).
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location "$root\backend"

if (-not (Test-Path ".venv")) {
    Write-Host "Creating virtual environment..." -ForegroundColor Cyan
    python -m venv .venv --system-site-packages
    & .\.venv\Scripts\python.exe -m pip install -r requirements.txt
}

if (-not (Test-Path "$root\.env")) {
    Write-Host "No .env found - copying from .env.example" -ForegroundColor Yellow
    Copy-Item "$root\.env.example" "$root\.env"
}

Write-Host "MetriX API  ->  http://localhost:8000/docs" -ForegroundColor Green
& .\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
