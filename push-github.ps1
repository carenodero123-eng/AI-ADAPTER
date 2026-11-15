
$ErrorActionPreference = "Stop"

# Always run from the project folder
Set-Location $PSScriptRoot

Write-Host "`n==================================" -ForegroundColor Cyan
Write-Host "       AI ADAPTER GITHUB PUSH" -ForegroundColor Cyan
Write-Host "==================================" -ForegroundColor Cyan

# Check Git
git status
if ($LASTEXITCODE -ne 0) {
    throw "Git status failed."
}

# Stage all new, modified and deleted files
Write-Host "`nPreparing project changes..." -ForegroundColor Yellow

git add -A

if ($LASTEXITCODE -ne 0) {
    throw "Could not stage project changes."
}

# Check whether there is anything to upload
git diff --cached --quiet

if ($LASTEXITCODE -eq 0) {
    Write-Host "`nNo new changes to upload!" -ForegroundColor Green
    exit 0
}

# Display files prepared for upload
Write-Host "`nThe following files are prepared for upload:" -ForegroundColor Cyan

$Files = @(git diff --cached --name-only)

$Files | ForEach-Object {
    Write-Host "  + $_" -ForegroundColor White
}

# Safety check for sensitive files
$UnsafeFiles = @($Files | Where-Object {
    $_ -match '(^|/)\.env($|/)' -or
    $_ -match '(^|/)\.venv(/|$)' -or
    $_ -match '\.(db|sqlite|sqlite3)$'
})

if ($UnsafeFiles.Count -gt 0) {
    Write-Host "`nWARNING: Sensitive or local files detected!" -ForegroundColor Red
    $UnsafeFiles | ForEach-Object { Write-Host $_ -ForegroundColor Red }
    throw "Upload cancelled. Check your .gitignore."
}

# Request approval
$Confirm = Read-Host "`nProceed with commit and GitHub upload? (Y/N)"

if ($Confirm -ne "Y") {
    Write-Host "Upload cancelled. No commit or push performed." -ForegroundColor Yellow
    exit 0
}

# Commit
git commit -m "Update AI Adapter project"

if ($LASTEXITCODE -ne 0) {
    throw "Git commit failed."
}

# Push
git push

if ($LASTEXITCODE -ne 0) {
    throw "Git push failed."
}

Write-Host "`nSUCCESS! Your project has been uploaded to GitHub." -ForegroundColor Green