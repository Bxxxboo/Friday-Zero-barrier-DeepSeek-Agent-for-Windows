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
        if ($env:GITHUB_TOKEN) {
            Write-Host "gh not found; using GitHub API with GITHUB_TOKEN ..." -ForegroundColor Yellow
            $apiArgs = @{ RepoOwner = $RepoOwner }
            if ($GitHubRepoName) { $apiArgs.RepoName = $GitHubRepoName }
            if ($SkipBuild) { $apiArgs.SkipBuild = $true }
            & (Join-Path $Root "scripts\publish-github-release.ps1") @apiArgs
        } else {
            Write-Host "gh CLI and GITHUB_TOKEN not available; skip GitHub Release." -ForegroundColor Yellow
            Write-Host "  Set `$env:GITHUB_TOKEN and run: scripts\publish-github-release.cmd" -ForegroundColor Yellow
        }
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
        . (Join-Path $Root "scripts\friday-dist.ps1")
        $Zip = Get-FridayReleaseZipPath -Root $Root
        if (-not (Test-Path $Zip)) {
            throw "Release zip not found: $Zip"
        }
        $ReleaseNotes = & (Join-Path $Root "scripts\release-notes.ps1") | Out-String
        $ReleaseNotes = $ReleaseNotes.Trim()
        $UpdateZip = Join-Path (Join-Path $Root "release") "Friday-Update-$Version.zip"
        $SetupExe = Join-Path (Join-Path $Root "release") "Friday-Setup-$Version.exe"
        $assets = @($Zip)
        if (Test-Path $UpdateZip) { $assets += $UpdateZip }
        if (Test-Path $SetupExe) { $assets += $SetupExe }

        gh release view $Tag --repo $Repo 2>$null
        if ($LASTEXITCODE -eq 0) {
            gh release upload $Tag @assets --repo $Repo --clobber
            gh release edit $Tag --repo $Repo --title "星期五 v$Version" --notes $ReleaseNotes
        } else {
            gh release create $Tag @assets --repo $Repo --title "星期五 v$Version" --notes $ReleaseNotes
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
