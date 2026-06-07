param(
    [string]$RepoOwner = "Bxxxboo",
    [string]$RepoName = "friday",
    [ValidateSet("public", "private")]
    [string]$Visibility = "public",
    [ValidateSet("", "patch", "minor", "major")]
    [string]$Bump = "",
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

if (-not (Test-Path ".git")) {
    git init -b main
}

git add -A
$status = git status --porcelain
if ($status) {
    git commit -m "chore: prepare Friday open-source release"
} else {
    Write-Host "No changes to commit." -ForegroundColor Yellow
}

$remoteUrl = git remote get-url origin 2>$null
if (-not $remoteUrl) {
    Write-Host "Creating GitHub repo and pushing..." -ForegroundColor Cyan
    gh repo create $Repo --$Visibility --source=. --remote=origin --push --description "Friday - Windows AI desktop butler"
} else {
    Write-Host "Pushing to origin..." -ForegroundColor Cyan
    git push -u origin HEAD
}

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

$Zip = Get-ChildItem (Join-Path $PWD "release") -Filter "*-Windows.zip" | Select-Object -First 1
if (-not $Zip) { throw "Release zip not found in release/" }

$Notes = @"
## Friday $Version

Windows AI desktop butler.

### Install
1. Download ``$($Zip.Name)``
2. Extract and run ``星期五.exe``
3. See ``安装教程.txt`` inside the archive
"@

gh release view $Tag 2>$null
if ($LASTEXITCODE -eq 0) {
    Write-Host "Release $Tag exists, uploading asset..." -ForegroundColor Yellow
    gh release upload $Tag $Zip.FullName --clobber
} else {
    gh release create $Tag $Zip.FullName --title "Friday $Version" --notes $Notes
}

Write-Host "Release: https://github.com/$Repo/releases/tag/$Tag" -ForegroundColor Green
