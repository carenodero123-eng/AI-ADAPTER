
$ErrorActionPreference = "Stop"

$ProjectRoot = $PSScriptRoot

Write-Host "Starting AI Adapter..." -ForegroundColor Cyan

# Start FastAPI backend
Write-Host "Starting FastAPI..." -ForegroundColor Yellow

Start-Process powershell.exe `
    -WorkingDirectory $ProjectRoot `
    -ArgumentList '-NoExit', '-Command', "& '$ProjectRoot\scripts\run-dev.ps1'"

# Wait for backend readiness
Write-Host "Waiting for backend..." -ForegroundColor Yellow

$Ready = $false

for ($i = 0; $i -lt 30; $i++) {
    try {
        $response = Invoke-RestMethod `
            -Uri "http://127.0.0.1:8000/health/ready" `
            -TimeoutSec 2

        if ($response.status -eq "ready") {
            $Ready = $true
            break
        }
    }
    catch {
        Start-Sleep -Seconds 2
    }
}

if (-not $Ready) {
    throw "Backend did not become ready. Check the FastAPI terminal."
}

Write-Host "Backend is ready!" -ForegroundColor Green

# Start Streamlit dashboard
Write-Host "Starting Streamlit..." -ForegroundColor Yellow

Start-Process powershell.exe `
    -WorkingDirectory $ProjectRoot `
    -ArgumentList '-NoExit', '-Command', "& '$ProjectRoot\.venv\Scripts\python.exe' -m streamlit run dashboard/app.py --server.address 127.0.0.1 --server.port 8501"

Start-Sleep -Seconds 3

Start-Process "http://127.0.0.1:8501"

Write-Host "AI Adapter launched successfully!" -ForegroundColor Green