$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

$Git = "C:\Program Files\Git\bin\git.exe"
if (-not (Test-Path $Git)) {
    $Git = (Get-Command git -ErrorAction SilentlyContinue).Source
}
if (-not $Git) { throw "Git not found. Install from https://git-scm.com/download/win" }

if (-not (Test-Path ".git")) {
    & $Git init -b main
}

& $Git add -A
$status = & $Git status --porcelain
if ($status) {
    $env:GIT_AUTHOR_NAME = "Friday Source"
    $env:GIT_AUTHOR_EMAIL = "friday-source@local"
    $env:GIT_COMMITTER_NAME = "Friday Source"
    $env:GIT_COMMITTER_EMAIL = "friday-source@local"
    & $Git commit -m "chore: Friday source repository for GitHub import"
    if ($LASTEXITCODE -ne 0) { throw "git commit failed (exit $LASTEXITCODE)" }
    Write-Host "Git commit created." -ForegroundColor Green
} else {
    Write-Host "Working tree clean, skip commit." -ForegroundColor Yellow
}

Write-Host ""
Write-Host "Next: push to Gitee for import URL" -ForegroundColor Cyan
Write-Host "  `$env:GITEE_TOKEN='token'; scripts\push-gitee-source.cmd -GiteeUser YOUR_GITEE_USERNAME"
