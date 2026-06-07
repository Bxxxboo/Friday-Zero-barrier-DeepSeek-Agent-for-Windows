param(
    [string]$RepoOwner = "Bxxxboo",
    [string]$RepoName = "",
    [string]$GiteeUser = "Bxxxboo",
    [string]$GiteeRepoName = "friday",
    [ValidateSet("", "patch", "minor", "major")]
    [string]$Bump = "",
    [switch]$SkipGitee
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

$args = @{
    RepoOwner = $RepoOwner
    GiteeUser = $GiteeUser
    GiteeRepoName = $GiteeRepoName
}
if ($RepoName) { $args.GitHubRepoName = $RepoName }
if ($Bump) { $args.Bump = $Bump }

& (Join-Path $Root "scripts\sync-remotes.ps1") @args

if ($SkipGitee) {
    Write-Host "Note: SkipGitee is deprecated; sync-remotes always pushes both remotes." -ForegroundColor Yellow
}

$VersionLine = Select-String -Path "friday\version.py" -Pattern '__version__ = "(.+)"' | Select-Object -First 1
$Version = $VersionLine.Matches[0].Groups[1].Value
Write-Host "For full release (zip + Gitee/GitHub Releases): scripts\publish-release.cmd -Bump patch" -ForegroundColor Cyan
