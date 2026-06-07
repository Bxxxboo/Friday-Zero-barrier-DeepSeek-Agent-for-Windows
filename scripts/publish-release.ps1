param(
    [string]$RepoOwner = "Bxxxboo",
    [string]$GitHubRepoName = "",
    [string]$GiteeUser = "Bxxxboo",
    [string]$GiteeRepoName = "friday",
    [ValidateSet("", "patch", "minor", "major")]
    [string]$Bump = "",
    [switch]$SkipBuild,
    [switch]$SkipGithubRelease,
    [switch]$SkipGiteeRelease,
    [switch]$GitOnly
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

$syncArgs = @{
    RepoOwner = $RepoOwner
    GiteeUser = $GiteeUser
    GiteeRepoName = $GiteeRepoName
}
if ($GitHubRepoName) { $syncArgs.GitHubRepoName = $GitHubRepoName }
if ($Bump) { $syncArgs.Bump = $Bump }

Write-Host "=== 1/3 Sync Git (GitHub + Gitee) ===" -ForegroundColor Cyan
& (Join-Path $Root "scripts\sync-remotes.ps1") @syncArgs

if ($GitOnly) {
    Write-Host "GitOnly set; done." -ForegroundColor Yellow
    exit 0
}

if (-not $SkipGiteeRelease) {
    Write-Host ""
    Write-Host "=== 2/3 Gitee Release (国内更新源) ===" -ForegroundColor Cyan
    $giteeArgs = @{ GiteeUser = $GiteeUser; RepoName = $GiteeRepoName }
    if ($SkipBuild) { $giteeArgs.SkipBuild = $true }
    & (Join-Path $Root "scripts\publish-gitee-release.ps1") @giteeArgs
} else {
    Write-Host "Skip Gitee release." -ForegroundColor Yellow
}

if (-not $SkipGithubRelease) {
    Write-Host ""
    Write-Host "=== 3/3 GitHub Release (备用) ===" -ForegroundColor Cyan
    if (-not (Get-Command gh -ErrorAction SilentlyContinue)) {
        Write-Host "gh CLI not found; skip GitHub Release (Gitee already published)." -ForegroundColor Yellow
    } else {
        $ghArgs = @{ RepoOwner = $RepoOwner; SkipRelease = $false }
        if ($GitHubRepoName) { $ghArgs.RepoName = $GitHubRepoName }
        if ($SkipBuild) { $ghArgs | Out-Null }
        # publish-github pushes again — call release steps only via inline
        $VersionLine = Select-String -Path "friday\version.py" -Pattern '__version__ = "(.+)"' | Select-Object -First 1
        $Version = $VersionLine.Matches[0].Groups[1].Value
        $Tag = "v$Version"
        $Repo = if ($GitHubRepoName) { "$RepoOwner/$GitHubRepoName" } else { "$RepoOwner/friday" }

        if (-not $SkipBuild) {
            powershell -ExecutionPolicy Bypass -File scripts\make-release.ps1
        }
        $Zip = Join-Path $PWD "release\Friday-Windows.zip"
        if (-not (Test-Path $Zip)) {
            throw "release/Friday-Windows.zip not found"
        }
        $Notes = @"
## Friday $Version

Windows AI desktop butler.

### Install
1. Download ``Friday-Windows.zip``
2. Extract and run ``星期五.exe``
3. See ``安装教程.txt`` in the archive
"@
        gh release view $Tag --repo $Repo 2>$null
        if ($LASTEXITCODE -eq 0) {
            gh release upload $Tag $Zip --repo $Repo --clobber
        } else {
            gh release create $Tag $Zip --repo $Repo --title "Friday $Version" --notes $Notes
        }
        Write-Host "GitHub release: https://github.com/$Repo/releases/tag/$Tag" -ForegroundColor Green
    }
} else {
    Write-Host "Skip GitHub release." -ForegroundColor Yellow
}

Write-Host ""
Write-Host "=== Publish complete ===" -ForegroundColor Green
Write-Host "  Gitee:  https://gitee.com/$GiteeUser/$GiteeRepoName/releases"
Write-Host "  GitHub: https://github.com/$RepoOwner/$(if ($GitHubRepoName) { $GitHubRepoName } else { 'friday' })/releases"
