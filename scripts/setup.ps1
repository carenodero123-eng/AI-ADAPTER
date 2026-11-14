# Creates the local virtual environment and installs project dependencies.
$ErrorActionPreference = "Stop"
Set-Location (Split-Path -Parent $PSScriptRoot)

if (-not (Test-Path ".venv")) {
    Write-Host "Creating .venv with Python 3.14..."
    py -3.14 -m venv .venv
}

$python = Join-Path $PWD ".venv\Scripts\python.exe"

Write-Host "Upgrading pip..."
& $python -m pip install --upgrade pip

Write-Host "Installing project with development dependencies..."
& $python -m pip install -e ".[dev]"

if (-not (Test-Path ".env")) {
    Copy-Item ".env.example" ".env"
    Write-Host "Created .env from .env.example"
}

Write-Host ""
Write-Host "Setup complete."
Write-Host "Activate with:  .\.venv\Scripts\Activate.ps1"
Write-Host "Run the API:    .\scripts\run-dev.ps1"
Write-Host "Run the tests:  .\scripts\test.ps1"
