# Runs the deterministic Stage I model-version and contract regression suite.
param(
    [switch]$Update
)
$ErrorActionPreference = "Stop"
Set-Location (Split-Path -Parent $PSScriptRoot)

$python = Join-Path $PWD ".venv\Scripts\python.exe"
if (-not (Test-Path $python)) {
    throw "Virtual environment not found. Run .\scripts\setup.ps1 first."
}

$previousBaselineMode = $env:UPDATE_REGRESSION_BASELINES
try {
    if ($Update) {
        $env:UPDATE_REGRESSION_BASELINES = "1"
    }
    else {
        Remove-Item Env:UPDATE_REGRESSION_BASELINES -ErrorAction SilentlyContinue
    }

    & $python -m pytest -q -m regression tests/test_model_versions.py tests/test_regression.py @args
    exit $LASTEXITCODE
}
finally {
    if ($null -eq $previousBaselineMode) {
        Remove-Item Env:UPDATE_REGRESSION_BASELINES -ErrorAction SilentlyContinue
    }
    else {
        $env:UPDATE_REGRESSION_BASELINES = $previousBaselineMode
    }
}
