param(
    [string]$RepoOwner = "Bxxxboo",
    [string]$RepoName = "",
    [ValidateSet("", "patch", "minor", "major")]
    [string]$Bump = "",
    [switch]$SkipGitee
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

$Git = "C:\Program Files\Git\bin\git.exe"
if (-not (Test-Path $Git)) {
    $Git = (Get-Command git -ErrorAction SilentlyContinue).Source
}
if (-not $Git) { throw "Git not found" }

if ($Bump) {
    & (Join-Path $Root "scripts\bump-version.ps1") -Part $Bump
}

$VersionLine = Select-String -Path "friday\version.py" -Pattern '__version__ = "(.+)"' | Select-Object -First 1
if (-not $VersionLine) { throw "Cannot read __version__ from friday/version.py" }
$Version = $VersionLine.Matches[0].Groups[1].Value
Write-Host "Current version: $Version" -ForegroundColor Cyan

if (-not $RepoName) {
    $origin = & $Git remote get-url origin 2>$null
    if ($origin -match 'github\.com[:/][^/]+/([^/.]+)') {
        $RepoName = $Matches[1]
    } else {
        $RepoName = "friday"
    }
}

$originUrl = "https://github.com/$RepoOwner/$RepoName.git"
$remotes = & $Git remote
if ($remotes -contains "origin") {
    & $Git remote set-url origin $originUrl
} else {
    & $Git remote add origin $originUrl
}

& $Git add -A
$status = & $Git status --porcelain
if ($status) {
    $env:GIT_AUTHOR_NAME = "Friday Source"
    $env:GIT_AUTHOR_EMAIL = "friday-source@local"
    $env:GIT_COMMITTER_NAME = "Friday Source"
    $env:GIT_COMMITTER_EMAIL = "friday-source@local"
    $msg = if ($Bump) { "chore: release v$Version" } else { "chore: sync v$Version" }
    & $Git commit -m $msg
    Write-Host "Committed: $msg" -ForegroundColor Green
} else {
    Write-Host "Working tree clean." -ForegroundColor Yellow
}

Write-Host "Pushing to GitHub ($RepoOwner/$RepoName) ..." -ForegroundColor Cyan
& $Git push -u origin main

if (-not $SkipGitee) {
    $giteeRemotes = & $Git remote
    if ($giteeRemotes -contains "gitee") {
        Write-Host "Pushing to Gitee mirror ..." -ForegroundColor Cyan
        & $Git push gitee main
    }
}

Write-Host ""
Write-Host "Done: https://github.com/$RepoOwner/$RepoName" -ForegroundColor Green
Write-Host "Version: v$Version (tag manually or run publish-github.ps1 for Release)" -ForegroundColor Cyan
