# Execution Guide

Companion runbook to [README.md](README.md). It covers everything from a clean machine to a running API, dashboard, real-provider requests, tests, and the optional container stack.

All commands assume Windows PowerShell and the repository root. The application consists of two processes:

| Process | Default address | Started by |
|---|---|---|
| FastAPI service | http://127.0.0.1:8000 | `scripts\run-dev.ps1` |
| Streamlit dashboard | http://127.0.0.1:8501 | `scripts\dashboard.ps1` |

The dashboard talks to the API over HTTP. Keep the API running while the dashboard is open.

---

## Step 1 - Prerequisites

You need:

- Windows 10/11 with PowerShell 5.1 or later.
- Python 3.14 plus the `py` launcher.
- The project source at `C:\AI ADAPTER PRJCT` (or your own path).
- Docker Desktop with Compose v2 only if you want the Stage M container demonstration.
- Network access to a provider endpoint only if you plan to run the real-provider steps.

Open PowerShell and check the interpreter:

```powershell
py -3.14 --version
```

Expected:

```text
Python 3.14.x
```

If `py` is not available but Python 3.14 is on `PATH`, use `python` instead of `py -3.14` in the setup step.

---

## Step 2 - One-time project setup

Move to the project and allow local scripts for this PowerShell process only. The execution policy change is not persisted.

```powershell
Set-Location "C:\AI ADAPTER PRJCT"
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
```

Run the idempotent setup script. It creates `.venv`, installs the project with development dependencies, and copies `.env.example` to `.env` when `.env` does not exist.

```powershell
.\scripts\setup.ps1
```

Manual equivalent, if you prefer explicit commands:

```powershell
py -3.14 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -e ".[dev]"
Copy-Item .env.example .env
```

Verify the virtual environment:

```powershell
.\.venv\Scripts\python.exe --version
```

Expected: `Python 3.14.x`.

Apply database migrations once. The default `.env` also auto-creates the SQLite schema at startup, so this is optional locally but mirrors production.

```powershell
.\.venv\Scripts\alembic.exe upgrade head
.\.venv\Scripts\alembic.exe current
```

Expected: Alembic reports the head revision and then `current` prints the same revision.

---

## Step 3 - Understand the baseline configuration

`.env` is loaded automatically by the API. Real environment variables set in PowerShell take precedence over `.env`, which is how the real-provider section overrides values without editing files.

Show the non-secret baseline values:

```powershell
Select-String -Path .env -Pattern '^(DEFAULT_PROVIDER|SECURITY_REQUIRE_AUTH|DATABASE_ENABLED|MODEL_VERSION_MANIFEST|RELIABILITY_FALLBACK_PROVIDER)='
```

Expected baseline for local development:

```text
DEFAULT_PROVIDER=fake
SECURITY_REQUIRE_AUTH=false
DATABASE_ENABLED=true
MODEL_VERSION_MANIFEST=config/model_versions.json
RELIABILITY_FALLBACK_PROVIDER=fake
```

Meaning:

- `fake` is the deterministic local provider, so the app works with no external key.
- Authentication is off locally, but provider management, history, monitoring, and model-version endpoints are still admin-only when authentication is enabled. Keep the service bound to loopback.
- Request history is stored in `data\ai_adapter.db`, which is git-ignored.
- Startup validates every configured provider/model against the manifest and fails closed if an entry is missing.

Never print or commit the `OPENAI_API_KEY` line.

---

## ===================================START==================================================
## Step 4 - Start the API

Open **Terminal A** and run:

```powershell
Set-Location "C:\AI ADAPTER PRJCT"
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\scripts\run-dev.ps1
```

Equivalent direct command:

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000 --no-access-log
```

Watch the startup log. A healthy start contains:

```text
"providers": ["fake"]
"fallback_provider": "fake"
"retry_max_attempts": 3
"auth_required": false
"database_enabled": true
"model_catalog_enabled": true
"model_catalog_entries": 4
INFO:     Application startup complete.
```

Do not continue until `Application startup complete.` appears.

### Verify from Terminal B

Open a **second** PowerShell window. No API key is needed for these local checks.

```powershell
Invoke-RestMethod "http://127.0.0.1:8000/health/ready" | ConvertTo-Json -Depth 5
```

Expected:

```json
{
  "status": "ready",
  "checks": { "configuration": "ok", "logging": "ok", "models": "ok", "database": "ok" }
}
```

Readiness and liveness live at the **root**, not under `/api/v1`:

- `GET /health/live`
- `GET /health/ready`

List the registered providers:

```powershell
Invoke-RestMethod "http://127.0.0.1:8000/api/v1/providers" | ConvertTo-Json -Depth 5
```

Expected: `fake` with `fake-small` and `fake-large`, marked `is_default: true`.

Interactive API documentation (development only):

```text
http://127.0.0.1:8000/docs
```

---

## Step 5 - Start the dashboard

Leave the API running. Open **Terminal C**:

```powershell
Set-Location "C:\AI ADAPTER PRJCT"
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\scripts\dashboard.ps1
```

The script refuses non-loopback addresses unless `-AllowRemote` is supplied. Defaults:

- API base: `http://127.0.0.1:8000`
- API prefix: `/api/v1`
- Dashboard: `http://127.0.0.1:8501`

Open the dashboard:

```text
http://127.0.0.1:8501
```

Valid URL changes:

```powershell
.\scripts\dashboard.ps1 -Port 8502
.\scripts\dashboard.ps1 -Port 8600 -HostAddress 127.0.0.1
```

If the script prints `Port 8501 is not available`, a previous dashboard is still running. See Step 12 before starting another one.

Dashboard pages and what they show:

- **Overview** - request counts, success/error rates, latency percentiles, tokens, cost, provider filters.
- **Providers** - registered providers, configured models, health checks, circuit state.
- **Requests** - persisted request history with filters and detail records.
- **Model versions** - manifest entries and their status.
- **Metrics** - bounded Prometheus text exposition.

---

## Step 6 - Baseline requests with the fake provider

These requests prove the full stack without any external service.

### Generate

```powershell
$body = @{
  provider = "fake"
  model = "fake-small"
  messages = @(@{ role = "user"; content = "Explain why deterministic fallback matters." })
  temperature = 0.2
  max_tokens = 64
} | ConvertTo-Json -Depth 5

Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:8000/api/v1/generate" `
  -ContentType "application/json" -Body $body | ConvertTo-Json -Depth 6
```

Expected fields: `provider: "fake"`, deterministic `content`, token usage, `providers_tried: ["fake"]`, `fallback_used: false`.

### Fault report

```powershell
$report = "Machine: Conveyor 3`nFault: Bearing overheating during the night shift.`nTemperature: 92 C`nDowntime: 2 hours`nAction taken: Replaced the bearing and lubricated the shaft.`nSeverity: high"

$faultBody = @{
  provider = "fake"
  model = "fake-small"
  report = $report
} | ConvertTo-Json -Depth 5

Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:8000/api/v1/fault-reports/summarize" `
  -ContentType "application/json" -Body $faultBody | ConvertTo-Json -Depth 6
```

Expected: a validated `summary` object with `machine`, `fault_description`, `temperature`, `downtime`, `action_taken`, `severity`, plus token and cost fields. `extraction` is `provider` when the provider returns valid JSON and `deterministic` when rule-based extraction is used instead.

### Observe

```powershell
Invoke-RestMethod "http://127.0.0.1:8000/api/v1/monitoring/summary?window=24h" | ConvertTo-Json -Depth 8
Invoke-RestMethod "http://127.0.0.1:8000/api/v1/requests?limit=5" | ConvertTo-Json -Depth 6
(Invoke-WebRequest "http://127.0.0.1:8000/api/v1/monitoring/metrics").Content
```

Refresh the dashboard and confirm the same requests appear.

---

## Step 7 - Real provider (Groq free tier)

The project's `openai` adapter speaks the OpenAI chat-completions protocol. Groq exposes an OpenAI-compatible endpoint at `https://api.groq.com/openai/v1`, so it can be used without code changes. The provider will still be labelled `openai` in the API and dashboard because that is the adapter registry key.

> Availability is account-specific. List your own models before configuring the adapter, and only use IDs that appear in that list.

### 7.1 Handle the key safely

Use a hidden prompt. Do not put the key in a command line, a script, a document, or chat, and do not paste it into `.env` unless you accept plaintext storage on disk.

```powershell
$secure = Read-Host "Groq API key" -AsSecureString
$env:OPENAI_API_KEY = [System.Net.NetworkCredential]::new("", $secure).Password
"Key length: $($env:OPENAI_API_KEY.Length)"
```

A normal Groq key is roughly 56 characters. Never print the value itself.

If a key is ever exposed in chat, a screenshot, a log, or shell history, revoke it in the provider console immediately and create a new one.

### 7.2 List the models enabled for your account

```powershell
Invoke-RestMethod -Uri "https://api.groq.com/openai/v1/models" `
  -Headers @{ Authorization = "Bearer $env:OPENAI_API_KEY" } |
  Select-Object -ExpandProperty data |
  Select-Object id, owned_by |
  Format-Table -AutoSize
```

Use the printed `id` values. As of 2026-11-14, the free tier on the reference account exposes `openai/gpt-oss-120b` and `openai/gpt-oss-20b`; the Llama 3.3 and 3.1 IDs return HTTP 404 for that account.

`invalid_api_key` means the key was not entered correctly or was revoked. Re-enter it with the hidden prompt.

### 7.3 Configure the adapter for this session

Run these in **Terminal A**, the same window that will start the API:

```powershell
$env:OPENAI_BASE_URL = "https://api.groq.com/openai/v1"
$env:OPENAI_MODELS = "openai/gpt-oss-120b,openai/gpt-oss-20b"
$env:OPENAI_DEFAULT_MODEL = "openai/gpt-oss-120b"
$env:MODEL_VERSION_MANIFEST = "config/model_versions.groq.json"

# Make provider failures visible instead of being masked by the fake fallback.
$env:RELIABILITY_MAX_ATTEMPTS = "1"
$env:RELIABILITY_SECONDARY_PROVIDER = " "
$env:RELIABILITY_FALLBACK_PROVIDER = " "

# Reasoning models count reasoning tokens against the completion cap.
$env:FAULT_REPORT_MAX_TOKENS = "1024"
```

Two details matter:

- PowerShell deletes an environment variable assigned `""`. A single space is used instead; the settings validator trims it, which disables the fallback. Without this, `.env` would re-apply `RELIABILITY_FALLBACK_PROVIDER=fake` and a provider failure would be silently replaced by fake output.
- Process environment variables override `.env`. Nothing in `.env` is modified.

### 7.4 The model version manifest

`config/model_versions.groq.json` contains the fake models plus the Groq model IDs used above. Startup fails closed when a configured model has no manifest entry, so any new model ID must be added there with `provider`, `model`, `version`, `status`, `released_on`, and optional `notes`.

If you change `OPENAI_MODELS`, either keep every ID inside the manifest or add the missing entry. A startup error naming a model means exactly this.

### 7.5 Restart the API

Settings are read only at startup. Stop Terminal A with `Ctrl+C`, then restart from the same window so it inherits the variables:

```powershell
.\scripts\run-dev.ps1
```

Expected additions in the startup log:

```text
"providers": ["fake", "openai"]
"secondary_provider": null
"fallback_provider": null
"retry_max_attempts": 1
"model_catalog_entries": 6
```

### 7.6 Verify the real provider

From Terminal B:

```powershell
Invoke-RestMethod "http://127.0.0.1:8000/api/v1/providers" | ConvertTo-Json -Depth 5
Invoke-RestMethod "http://127.0.0.1:8000/api/v1/providers/openai/health" | ConvertTo-Json -Depth 5
```

Expected: the `openai` entry lists exactly the configured models, and health is:

```json
{
  "provider": "openai",
  "status": "healthy",
  "latency_ms": 470.458,
  "detail": null,
  "circuit": { "state": "closed", "failure_count": 0, "recovery_remaining_seconds": null }
}
```

The health check performs a real authenticated `GET /models` against Groq. A non-blank key alone does not prove the key is valid; this call does.

### 7.7 Real generation

```powershell
$body = @{
  provider = "openai"
  model = "openai/gpt-oss-120b"
  messages = @(@{ role = "user"; content = "Reply with exactly this sentence: The AI adapter is online." })
  temperature = 0.2
  max_tokens = 256
} | ConvertTo-Json -Depth 5

Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:8000/api/v1/generate" `
  -ContentType "application/json" -Body $body | ConvertTo-Json -Depth 6
```

Expected shape:

```json
{
  "provider": "openai",
  "model": "openai/gpt-oss-120b",
  "content": "The AI adapter is online.",
  "usage": { "prompt_tokens": 81, "completion_tokens": 63, "total_tokens": 144 },
  "finish_reason": "stop",
  "providers_tried": ["openai"],
  "fallback_used": false,
  "cost_usd": 0.00005
}
```

`cost_usd` is computed from configured pricing (`$0.15` input / `$0.60` output per million tokens), not from the provider invoice. A free plan still bills $0.

### 7.8 Real fault-report summarization

```powershell
$report = "Machine: Conveyor 3`nFault: Bearing overheating during the night shift.`nTemperature: 92 C`nDowntime: 2 hours`nAction taken: Replaced the bearing and lubricated the shaft.`nSeverity: high"

$faultBody = @{
  provider = "openai"
  model = "openai/gpt-oss-120b"
  report = $report
} | ConvertTo-Json -Depth 5

Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:8000/api/v1/fault-reports/summarize" `
  -ContentType "application/json" -Body $faultBody | ConvertTo-Json -Depth 6
```

Expected: `extraction: "provider"`, `missing_fields: []`, every summary field populated from the report, and `fallback_used: false`.

If the model returns unusable JSON, the service falls back to deterministic extraction, sets `extraction: "deterministic"`, and records `extraction_reason`. That is designed behavior, not a failure.

### 7.9 How to prove the result is real

- `providers_tried` is exactly `["openai"]` and `fallback_used` is `false`.
- Provider health reaches `api.groq.com`.
- Token usage and latency match a remote call.
- Fake fallback is disabled in this session, so a successful result cannot be fake output.

---

## Step 8 - Observe the real traffic

```powershell
Invoke-RestMethod "http://127.0.0.1:8000/api/v1/monitoring/summary?window=24h" | ConvertTo-Json -Depth 8
Invoke-RestMethod "http://127.0.0.1:8000/api/v1/requests?limit=10" | ConvertTo-Json -Depth 6
(Invoke-WebRequest "http://127.0.0.1:8000/api/v1/monitoring/metrics").Content
Invoke-RestMethod "http://127.0.0.1:8000/api/v1/model-versions" | ConvertTo-Json -Depth 6
```

What to check:

- `by_provider` separates `fake` and `openai`.
- `by_kind` contains `generation` and `fault_report`.
- Request records include provider, model, tokens, cost, duration, and `fallback_used`.
- Metrics contain `ai_adapter_requests_total` and `ai_adapter_errors_total`.
- No key, authorization header, or report body appears in history or metrics.

Model IDs rejected by the provider appear as `provider_invalid_request` with HTTP 400 in the API and as `status: "error"` in history. Client errors are never masked by fallback.

Refresh `http://127.0.0.1:8501`; the dashboard reflects the same records.

---

## Step 9 - Tests and quality gate

Run the full suite:

```powershell
.\.venv\Scripts\python.exe -m pytest -q --strict-config --strict-markers
```

Expected on a host without Docker:

```text
340 passed, 1 skipped
```

The skip is the conditional Compose-validation test in `tests\test_deployment.py`, which requires a Docker CLI.

Run the Stage J quality gate (byte-compile, Ruff, full suite, fault matrix, regression suite):

```powershell
.\scripts\quality.ps1
```

Expected final line:

```text
Stage J quality gate passed.
```

Individual gates, if you need them separately:

```powershell
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m pytest -q -m fault_matrix tests\test_fault_matrix.py
.\.venv\Scripts\python.exe -m pytest -q -m regression tests\test_model_versions.py tests\test_regression.py
```

The tests never call a live provider and need no `.env` or repository secrets.

---



---

## Step 11 - Stop everything

In each terminal window press `Ctrl+C`:

1. Terminal C - dashboard.
2. Terminal B - optional request shell.
3. Terminal A - API (the reload watcher and worker both stop).

Environment variables, including the provider key, disappear when the window closes. Restarting without them returns the app to the `.env` baseline (`fake` provider).

To clear provider variables in a window that stays open:

```powershell
Remove-Item Env:OPENAI_API_KEY, Env:OPENAI_BASE_URL, Env:OPENAI_MODELS, `
  Env:OPENAI_DEFAULT_MODEL, Env:MODEL_VERSION_MANIFEST, Env:RELIABILITY_MAX_ATTEMPTS, `
  Env:RELIABILITY_SECONDARY_PROVIDER, Env:RELIABILITY_FALLBACK_PROVIDER, `
  Env:FAULT_REPORT_MAX_TOKENS -ErrorAction SilentlyContinue
```

The SQLite file under `data\` remains; delete it only if you want to discard request history.

---

## Step 12 - Port conflicts and stale processes

A previous session's API or dashboard can keep a port occupied. Requests then reach the old process, which may not have the current configuration, producing misleading results such as `provider_not_found`.

Find the listener:

```powershell
Get-NetTCPConnection -LocalPort 8000 -State Listen | Select-Object OwningProcess
Get-NetTCPConnection -LocalPort 8501 -State Listen | Select-Object OwningProcess
```

Inspect the owning process before stopping anything:

```powershell
Get-CimInstance Win32_Process -Filter "ProcessId=<pid>" |
  Select-Object ProcessId, ParentProcessId, CommandLine | Format-List
```

Stop it only when the command line confirms it is this project's `uvicorn` or `streamlit`:

```powershell
Stop-Process -Id <pid> -Force
```

For an API started with `--reload`, also stop its child worker, or stop the parent and verify the port is released:

```powershell
Start-Sleep -Seconds 1
Get-NetTCPConnection -LocalPort 8000 -State Listen
```

Never stop a process you cannot identify.

---



Yes. The API already records every request it serves, and the dashboard reads those records. A PowerShell loop that posts questions to /api/v1/generate is enough — no server change needed.

Paste this into a second PowerShell window while the API is running (Terminal B, not the API window)

----
## =========================QUICK CHAT TEST WITH UI ASHBOARD RECORDS=========================
--powershell--
$provider = "openai"
$model    = "openai/gpt-oss-120b"

Write-Host "Ask questions. Type 'exit' to stop." -ForegroundColor Cyan
while ($true) {
    $question = Read-Host "You"
    if ([string]::IsNullOrWhiteSpace($question) -or $question.Trim() -eq "exit") { break }

    $body = @{
        provider    = $provider
        model       = $model
        messages    = @(@{ role = "user"; content = $question })
        temperature = 0.2
        max_tokens  = 256
    } | ConvertTo-Json -Depth 5

    try {
        $r = Invoke-RestMethod -Method Post `
            -Uri "http://127.0.0.1:8000/api/v1/generate" `
            -ContentType "application/json" -Body $body

        Write-Host "`nAssistant: $($r.content)`n" -ForegroundColor Green
        Write-Host ("{0} / {1} | {2:N1} ms | {3} tokens | cost_usd {4} | fallback {5}" -f `
            $r.provider, $r.model, $r.latency_ms, $r.usage.total_tokens, $r.cost_usd, $r.fallback_used) `
            -ForegroundColor DarkGray
    }
    catch {
        Write-Host "Request failed: $($_.ErrorDetails.Message)" -ForegroundColor Red
    }
}

----

## =====================================END================================================