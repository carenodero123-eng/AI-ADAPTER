# Runs the Stage J quality gate locally with the same checks used in CI.
$ErrorActionPreference = "Stop"
Set-Location (Split-Path -Parent $PSScriptRoot)

$python = Join-Path $PWD ".venv\Scripts\python.exe"
if (-not (Test-Path $python)) {
    throw "Virtual environment not found. Run .\scripts\setup.ps1 first."
}

$env:PYTHONHASHSEED = "0"
$env:PYTHONDONTWRITEBYTECODE = "1"
$env:UPDATE_REGRESSION_BASELINES = "0"

Write-Host "Byte-compiling application and tests..."
& $python -m compileall -q app dashboard tests alembic
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host "Linting with Ruff..."
& $python -m ruff check .
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host "Running full test suite..."
& $python -m pytest -q --strict-config --strict-markers
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host "Running deterministic fault matrix..."
& $python -m pytest -q -m fault_matrix tests/test_fault_matrix.py
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host "Running model-version and regression suite..."
& $python -m pytest -q -m regression tests/test_model_versions.py tests/test_regression.py
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host "Stage J quality gate passed."
exit 0
