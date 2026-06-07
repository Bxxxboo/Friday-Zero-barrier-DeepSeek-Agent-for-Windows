param(
    [string]$RepoOwner = "Bxxxboo",
    [string]$RepoName = "friday",
    [ValidateSet("public", "private")]
    [string]$Visibility = "public",
    [ValidateSet("", "patch", "minor", "major")]
    [string]$Bump = "",
    [string]$GiteeUser = "Bxxxboo",
    [string]$GiteeRepoName = "friday",
    [switch]$SkipRelease
)

$ErrorActionPreference = "Stop"
Set-Location (Split-Path -Parent $PSScriptRoot)

function Require-Command([string]$Name) {
    if (-not (Get-Command $Name -ErrorAction SilentlyContinue)) {
        throw "Missing command: $Name. Install Git and GitHub CLI first."
    }
}

Require-Command git
Require-Command gh

if ($Bump) {
    powershell -ExecutionPolicy Bypass -File scripts\bump-version.ps1 -Part $Bump
}

$Repo = "$RepoOwner/$RepoName"
Write-Host "Target repo: $Repo" -ForegroundColor Cyan

# Git: GitHub + Gitee
& (Join-Path $PWD "scripts\sync-remotes.ps1") -RepoOwner $RepoOwner -GitHubRepoName $RepoName -GiteeUser $GiteeUser -GiteeRepoName $GiteeRepoName

Write-Host ""
Write-Host "Repository: https://github.com/$Repo" -ForegroundColor Green

if ($SkipRelease) {
    Write-Host "SkipRelease set; done." -ForegroundColor Yellow
    exit 0
}

$versionLine = Select-String -Path "friday\version.py" -Pattern '__version__ = "(.+)"' | Select-Object -First 1
if (-not $versionLine) { throw "Cannot read __version__ from friday/version.py" }
$Version = $versionLine.Matches[0].Groups[1].Value
$Tag = "v$Version"

Write-Host "Building release $Tag ..." -ForegroundColor Cyan
powershell -ExecutionPolicy Bypass -File scripts\make-release.ps1

$Zip = Join-Path $PWD "release\Friday-Windows.zip"
if (-not (Test-Path $Zip)) { throw "Release zip not found in release/" }

$Notes = @"
## Friday $Version

Windows AI desktop butler.

### Install
1. Download ``Friday-Windows.zip``
2. Extract and run ``星期五.exe``
3. See ``安装教程.txt`` inside the archive
"@

gh release view $Tag --repo $Repo 2>$null
if ($LASTEXITCODE -eq 0) {
    Write-Host "Release $Tag exists, uploading asset..." -ForegroundColor Yellow
    gh release upload $Tag $Zip --repo $Repo --clobber
} else {
    gh release create $Tag $Zip --repo $Repo --title "Friday $Version" --notes $Notes
}

Write-Host "GitHub release: https://github.com/$Repo/releases/tag/$Tag" -ForegroundColor Green

if ($env:GITEE_TOKEN) {
    Write-Host "Publishing Gitee release (mirror) ..." -ForegroundColor Cyan
    powershell -ExecutionPolicy Bypass -File scripts\publish-gitee-release.ps1 -GiteeUser $GiteeUser -RepoName $GiteeRepoName -SkipBuild
} else {
    Write-Host "GITEE_TOKEN not set; skip Gitee Release. Run publish-gitee-release.cmd separately." -ForegroundColor Yellow
}

Write-Host "Tip: use scripts\publish-release.cmd next time for one-step sync." -ForegroundColor Cyan
