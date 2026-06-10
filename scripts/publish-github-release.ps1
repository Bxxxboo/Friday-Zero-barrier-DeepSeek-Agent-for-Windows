param(
    [string]$RepoOwner = "Bxxxboo",
    [string]$RepoName = "Friday-WeChat-Windows-AI-Butler",
    [string]$GitHubToken = $env:GITHUB_TOKEN,
    [switch]$SkipBuild,
    [switch]$SkipUpload
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

if (-not $GitHubToken) {
    throw "Set GITHUB_TOKEN first. Create at https://github.com/settings/tokens (scope: repo)"
}

$env:GITHUB_TOKEN = $GitHubToken

. (Join-Path $Root "scripts\friday-dist.ps1")

if (-not $SkipBuild) {
    powershell -ExecutionPolicy Bypass -File scripts\make-release.ps1
}

$Zip = Get-FridayReleaseZipPath -Root $Root
if (-not $SkipUpload -and -not (Test-Path $Zip)) {
    throw "Release zip not found: $Zip. Run scripts/make-release.ps1 first."
}

$Python = Join-Path $Root ".python-env\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $Python)) {
    $Python = Join-Path $Root ".venv\Scripts\python.exe"
}
if (-not (Test-Path -LiteralPath $Python)) { $Python = "python" }

$pyArgs = @(
    (Join-Path $Root "scripts\publish_github_release.py"),
    "--repo", "$RepoOwner/$RepoName"
)
if ($SkipUpload) { $pyArgs += "--skip-upload" }

& $Python @pyArgs
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

$VersionLine = Select-String -Path "friday\version.py" -Pattern '__version__ = "(.+)"' | Select-Object -First 1
$Version = $VersionLine.Matches[0].Groups[1].Value
Write-Host ""
Write-Host "GitHub release done!" -ForegroundColor Green
Write-Host "  https://github.com/$RepoOwner/$RepoName/releases/tag/v$Version"
