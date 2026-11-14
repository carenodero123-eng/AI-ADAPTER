# Starts the FastAPI service with auto-reload for local development.
param(
    [int]$Port = 8000,
    [string]$HostAddress = "127.0.0.1"
)

$ErrorActionPreference = "Stop"
Set-Location (Split-Path -Parent $PSScriptRoot)

$python = Join-Path $PWD ".venv\Scripts\python.exe"
if (-not (Test-Path $python)) {
    throw "Virtual environment not found. Run .\scripts\setup.ps1 first."
}

& $python -m uvicorn app.main:app --reload --host $HostAddress --port $Port --no-access-log
exit $LASTEXITCODE
