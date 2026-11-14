# Performs one live OpenAI request using the configured provider settings.
param(
    [string]$Model = "",
    [string]$Prompt = "Reply with exactly: adapter verification ok",
    [int]$MaxTokens = 64
)

$ErrorActionPreference = "Stop"
Set-Location (Split-Path -Parent $PSScriptRoot)

$python = Join-Path $PWD ".venv\Scripts\python.exe"
if (-not (Test-Path $python)) {
    throw "Virtual environment not found. Run .\scripts\setup.ps1 first."
}

Write-Host "This performs one live, billable OpenAI request."
$pythonArgs = @(
    "scripts\verify_openai.py",
    "--prompt", $Prompt,
    "--max-tokens", $MaxTokens
)
if ($Model) {
    $pythonArgs += @("--model", $Model)
}

& $python @pythonArgs
exit $LASTEXITCODE
