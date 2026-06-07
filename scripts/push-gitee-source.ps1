param(
    [Parameter(Mandatory = $true)]
    [string]$GiteeUser,
    [string]$RepoName = "friday",
    [string]$GiteeToken = $env:GITEE_TOKEN
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

$Git = "C:\Program Files\Git\bin\git.exe"
if (-not (Test-Path $Git)) {
    $Git = (Get-Command git -ErrorAction SilentlyContinue).Source
}
if (-not $Git) { throw "Git not found" }

& (Join-Path $Root "scripts\setup-source-git.ps1")

$CloneUrl = "https://gitee.com/$GiteeUser/$RepoName.git"
$WebUrl = "https://gitee.com/$GiteeUser/$RepoName"

Write-Host "Target: $CloneUrl" -ForegroundColor Cyan

if (-not $GiteeToken) {
    Write-Host ""
    Write-Host "GITEE_TOKEN not set. Create one at: https://gitee.com/profile/personal_access_tokens" -ForegroundColor Yellow
    Write-Host "Then run:" -ForegroundColor Yellow
    Write-Host "  `$env:GITEE_TOKEN='your-token'; scripts\push-gitee-source.cmd -GiteeUser $GiteeUser"
    Write-Host ""
    Write-Host "Or create empty repo on Gitee manually, then:" -ForegroundColor Yellow
    Write-Host "  git remote add gitee $CloneUrl"
    Write-Host "  git push -u gitee main"
    exit 0
}

$Headers = @{ Authorization = "token $GiteeToken" }
$Check = $null
try {
    $Check = Invoke-RestMethod -Uri "https://gitee.com/api/v5/repos/$GiteeUser/$RepoName" -Headers $Headers
} catch {
    if ($_.Exception.Response.StatusCode.value__ -ne 404) { throw }
}
if (-not $Check) {
    Write-Host "Creating Gitee repo $RepoName ..." -ForegroundColor Cyan
    $Body = @{
        access_token = $GiteeToken
        name = $RepoName
        description = "Friday source repo (for GitHub import)"
        private = $false
        auto_init = $false
    }
    Invoke-RestMethod -Method Post -Uri "https://gitee.com/api/v5/user/repos" -Body $Body | Out-Null
}

$RemoteUrl = "https://oauth2:${GiteeToken}@gitee.com/$GiteeUser/$RepoName.git"
$remotes = & $Git remote
if ($remotes -contains "gitee") { & $Git remote remove gitee }
& $Git remote add gitee $RemoteUrl
& $Git push -u gitee main --force

& $Git remote set-url gitee $CloneUrl

$VersionLine = Select-String -Path "friday\version.py" -Pattern '__version__ = "(.+)"' | Select-Object -First 1
$Version = if ($VersionLine) { $VersionLine.Matches[0].Groups[1].Value } else { "1.0.0" }

$InfoPath = Join-Path $Root "source-repo\repo-info.json"
$Info = @{
    clone_url = $CloneUrl
    web_url = $WebUrl
    version = $Version
    pushed_at = (Get-Date -Format "yyyy-MM-dd HH:mm")
    github_import = "https://github.com/new/import"
    github_target = "Bxxxboo/friday"
} | ConvertTo-Json -Depth 3
Set-Content -Path $InfoPath -Value $Info -Encoding UTF8

Write-Host ""
Write-Host "Done!" -ForegroundColor Green
Write-Host "  Clone URL (paste to GitHub Import): $CloneUrl"
Write-Host "  Open source site: source-repo\index.html"
Write-Host "  GitHub import: https://github.com/new/import"
