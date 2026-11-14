# Builds and starts the Stage M Compose stack, runs the end-to-end verifier,
# and optionally leaves the stack running for manual inspection.
param(
    [switch]$SkipBuild,
    [switch]$KeepRunning,
    [switch]$Reset,
    [int]$TimeoutSeconds = 180
)

$ErrorActionPreference = "Stop"
Set-Location (Split-Path -Parent $PSScriptRoot)

function New-RandomHex {
    param([int]$ByteCount = 32)
    $buffer = New-Object byte[] $ByteCount
    $rng = [System.Security.Cryptography.RandomNumberGenerator]::Create()
    try {
        $rng.GetBytes($buffer)
    }
    finally {
        $rng.Dispose()
    }
    return ([System.BitConverter]::ToString($buffer) -replace "-", "").ToLowerInvariant()
}

function Read-EnvValue {
    param([string]$Path, [string]$Name)
    $pattern = "^" + [regex]::Escape($Name) + "="
    $line = Get-Content -LiteralPath $Path |
        Where-Object { $_ -match $pattern } |
        Select-Object -First 1
    if (-not $line) {
        throw "$Name is missing from $Path."
    }
    $value = $line.Substring($Name.Length + 1).Trim()
    if (-not $value) {
        throw "$Name is blank in $Path."
    }
    return $value
}

$docker = Get-Command docker -ErrorAction SilentlyContinue
if (-not $docker) {
    throw "Docker CLI not found. Install Docker Desktop with Compose v2, then rerun this script."
}
& docker compose version *> $null
if ($LASTEXITCODE -ne 0) {
    throw "Docker Compose v2 is not available. Enable it in Docker Desktop, then rerun this script."
}

$python = Join-Path $PWD ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $python)) {
    throw "Virtual environment not found. Run .\scripts\setup.ps1 first."
}

$envFile = Join-Path $PWD ".env.docker"
if (Test-Path -LiteralPath $envFile) {
    $dbPassword = Read-EnvValue -Path $envFile -Name "POSTGRES_PASSWORD"
    $userKey = Read-EnvValue -Path $envFile -Name "SECURITY_API_KEYS"
    $adminKey = Read-EnvValue -Path $envFile -Name "SECURITY_ADMIN_API_KEYS"
    if ($dbPassword -like "replace-with*" -or $userKey -like "replace-with*" -or $adminKey -like "replace-with*") {
        throw "The placeholder values in .env.docker must be replaced. Delete the file to let this script generate new secrets."
    }
}
else {
    $dbPassword = New-RandomHex
    $userKey = New-RandomHex
    $adminKey = New-RandomHex
    $lines = @(
        "POSTGRES_USER=adapter",
        "POSTGRES_DB=ai_adapter",
        "POSTGRES_PASSWORD=$dbPassword",
        "SECURITY_API_KEYS=$userKey",
        "SECURITY_ADMIN_API_KEYS=$adminKey"
    )
    Set-Content -LiteralPath $envFile -Value $lines -Encoding ascii
    Write-Host "Generated random Compose secrets in .env.docker (git-ignored)."
}

if ($userKey -eq $adminKey) {
    throw "SECURITY_API_KEYS and SECURITY_ADMIN_API_KEYS must differ."
}
if ($userKey.Length -lt 16 -or $adminKey.Length -lt 16) {
    throw "API keys in .env.docker must be at least 16 characters."
}
if ($userKey -match '[\s,]' -or $adminKey -match '[\s,]') {
    throw "This demo expects exactly one user key and one admin key, without whitespace or commas."
}
if ($dbPassword -notmatch '^[A-Za-z0-9._~-]+$') {
    throw "POSTGRES_PASSWORD must be URL-safe because it is embedded in the database URL."
}

$compose = @(
    "compose",
    "--env-file", $envFile,
    "--project-name", "ai-adapter-demo"
)

if ($Reset) {
    Write-Host "Removing the previous demo stack and database volume..."
    & docker @($compose + @("down", "-v", "--remove-orphans"))
    if ($LASTEXITCODE -ne 0) {
        throw "docker compose down failed."
    }
}

$upArgs = $compose + @("up", "-d")
if (-not $SkipBuild) {
    $upArgs += "--build"
}

$previousUserKey = $env:E2E_USER_KEY
$previousAdminKey = $env:E2E_ADMIN_KEY
$failed = $false

try {
    Write-Host "Starting the AI Adapter stack..."
    & docker @upArgs
    if ($LASTEXITCODE -ne 0) {
        throw "docker compose up failed."
    }

    $env:E2E_USER_KEY = $userKey
    $env:E2E_ADMIN_KEY = $adminKey
    & $python scripts\e2e_demo.py --wait-timeout $TimeoutSeconds
    if ($LASTEXITCODE -ne 0) {
        throw "The end-to-end verifier reported a failure."
    }

    Write-Host ""
    Write-Host "API:       http://127.0.0.1:8000"
    Write-Host "Dashboard: http://127.0.0.1:8501"
}
catch {
    $failed = $true
    Write-Host ""
    Write-Host "Deployment verification failed. Recent service status and logs:" -ForegroundColor Yellow
    & docker @($compose + @("ps"))
    & docker @($compose + @("logs", "--no-color", "--tail", "40", "api", "dashboard", "db"))
    throw
}
finally {
    if ($null -eq $previousUserKey) {
        Remove-Item Env:\E2E_USER_KEY -ErrorAction SilentlyContinue
    }
    else {
        $env:E2E_USER_KEY = $previousUserKey
    }
    if ($null -eq $previousAdminKey) {
        Remove-Item Env:\E2E_ADMIN_KEY -ErrorAction SilentlyContinue
    }
    else {
        $env:E2E_ADMIN_KEY = $previousAdminKey
    }

    if (-not $KeepRunning) {
        $downArgs = $compose + @("down")
        if ($Reset) {
            $downArgs += "-v"
        }
        & docker @downArgs *> $null
    }
    elseif ($failed) {
        Write-Host "The failed stack was left running because -KeepRunning was supplied."
    }
    else {
        Write-Host ""
        Write-Host "Stack left running. Stop it with:"
        Write-Host "docker compose --env-file .env.docker --project-name ai-adapter-demo down"
    }
}
