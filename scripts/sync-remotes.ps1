param(
    [string]$RepoOwner = "Bxxxboo",
    [string]$GitHubRepoName = "",
    [string]$GiteeUser = "Bxxxboo",
    [string]$GiteeRepoName = "friday",
    [ValidateSet("", "patch", "minor", "major")]
    [string]$Bump = "",
    [string]$CommitMessage = ""
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
Write-Host "Version: v$Version" -ForegroundColor Cyan

if (-not $GitHubRepoName) {
    $origin = & $Git remote get-url origin 2>$null
    if ($origin -match 'github\.com[:/][^/]+/([^/.]+)') {
        $GitHubRepoName = $Matches[1]
    } else {
        $GitHubRepoName = "friday"
    }
}

$githubUrl = "https://github.com/$RepoOwner/$GitHubRepoName.git"
$giteeUrl = "https://gitee.com/$GiteeUser/$GiteeRepoName.git"
$remotes = @(& $Git remote)

foreach ($pair in @(@("origin", $githubUrl), @("gitee", $giteeUrl))) {
    $name, $url = $pair
    if ($remotes -contains $name) {
        & $Git remote set-url $name $url
    } else {
        & $Git remote add $name $url
    }
}

& $Git add -A
$status = & $Git status --porcelain
if ($status) {
    $env:GIT_AUTHOR_NAME = "Friday Source"
    $env:GIT_AUTHOR_EMAIL = "friday-source@local"
    $env:GIT_COMMITTER_NAME = "Friday Source"
    $env:GIT_COMMITTER_EMAIL = "friday-source@local"
    if (-not $CommitMessage) {
        $CommitMessage = if ($Bump) { "chore: release v$Version" } else { "chore: sync v$Version" }
    }
    & $Git commit -m $CommitMessage
    Write-Host "Committed: $CommitMessage" -ForegroundColor Green
} else {
    Write-Host "Working tree clean (skip commit)." -ForegroundColor Yellow
}

Write-Host "Pushing GitHub: $RepoOwner/$GitHubRepoName ..." -ForegroundColor Cyan
& $Git push -u origin main

Write-Host "Pushing Gitee:  $GiteeUser/$GiteeRepoName ..." -ForegroundColor Cyan
& $Git push -u gitee main

Write-Host ""
Write-Host "Git sync done." -ForegroundColor Green
Write-Host "  GitHub: https://github.com/$RepoOwner/$GitHubRepoName"
Write-Host "  Gitee:  https://gitee.com/$GiteeUser/$GiteeRepoName"
