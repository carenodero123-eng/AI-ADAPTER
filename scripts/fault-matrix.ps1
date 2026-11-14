# Runs only the deterministic Stage H fault-injection matrix.
$ErrorActionPreference = "Stop"
Set-Location (Split-Path -Parent $PSScriptRoot)

$python = Join-Path $PWD ".venv\Scripts\python.exe"
if (-not (Test-Path $python)) {
    throw "Virtual environment not found. Run .\scripts\setup.ps1 first."
}

& $python -m pytest -q -m fault_matrix tests/test_fault_matrix.py @args
exit $LASTEXITCODE
