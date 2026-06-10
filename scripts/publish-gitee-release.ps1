param(
    [string]$GiteeUser = "Bxxxboo",
    [string]$RepoName = "friday",
    [string]$GiteeToken = $env:GITEE_TOKEN,
    [switch]$SkipBuild,
    [switch]$SkipUpload
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

if (-not $GiteeToken) {
    throw "Set GITEE_TOKEN first. Create at https://gitee.com/profile/personal_access_tokens"
}

$env:GITEE_TOKEN = $GiteeToken

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
    (Join-Path $Root "scripts\publish_gitee_release.py"),
    "--repo", "$GiteeUser/$RepoName"
)
if ($SkipUpload) { $pyArgs += "--skip-upload" }

& $Python @pyArgs
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

$VersionLine = Select-String -Path "friday\version.py" -Pattern '__version__ = "(.+)"' | Select-Object -First 1
$Version = $VersionLine.Matches[0].Groups[1].Value
Write-Host ""
Write-Host "Gitee release done!" -ForegroundColor Green
Write-Host "  https://gitee.com/$GiteeUser/$RepoName/releases/tag/v$Version"
