# Starts the Stage L Streamlit dashboard against the local AI Adapter API.
param(
    [int]$Port = 8501,
    [string]$HostAddress = "127.0.0.1",
    [switch]$AllowRemote
)

$ErrorActionPreference = "Stop"
Set-Location (Split-Path -Parent $PSScriptRoot)

if ($HostAddress -notin @("127.0.0.1", "localhost", "::1") -and -not $AllowRemote) {
    throw "Refusing to expose the dashboard outside loopback. Use -AllowRemote only behind TLS and access control."
}

$python = Join-Path $PWD ".venv\Scripts\python.exe"
if (-not (Test-Path $python)) {
    throw "Virtual environment not found. Run .\scripts\setup.ps1 first."
}

& $python -m streamlit run dashboard/app.py --server.address $HostAddress --server.port $Port --server.headless true --browser.gatherUsageStats false
exit $LASTEXITCODE
