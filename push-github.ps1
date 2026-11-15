
# Check whether there are changes to commit
git diff --cached --quiet

if ($LASTEXITCODE -eq 0) {
    Write-Host "No new changes to upload." -ForegroundColor Yellow
    exit 0
}

# Show exactly what will be uploaded
Write-Host "`nFiles prepared for upload:" -ForegroundColor Cyan
git diff --cached --name-only

# Ask for confirmation
$Confirm = Read-Host "`nDo you want to commit and push these changes? (Y/N)"

if ($Confirm -ne "Y") {
    Write-Host "Upload cancelled. Your files remain unchanged." -ForegroundColor Yellow
    exit 0
}

# Commit changes
git commit -m "Update AI Adapter project"

if ($LASTEXITCODE -ne 0) {
    throw "Git commit failed."
}

# Push to GitHub
git push

if ($LASTEXITCODE -ne 0) {
    throw "Git push failed."
}

Write-Host "`nSuccessfully uploaded changes to GitHub!" -ForegroundColor Green