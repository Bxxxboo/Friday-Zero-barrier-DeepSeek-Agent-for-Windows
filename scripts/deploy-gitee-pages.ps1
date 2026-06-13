param(
    [string]$GiteeUser = "Bxxxboo",
    [string]$RepoName = "friday",
    [string]$GiteeToken = $env:GITEE_TOKEN,
    [string]$Branch = "pages",
    [switch]$SkipPush,
    [switch]$SkipBuild
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

if (-not $GiteeToken) {
    throw "Set GITEE_TOKEN first. Create at https://gitee.com/profile/personal_access_tokens"
}
$env:GITEE_TOKEN = $GiteeToken

$websiteDir = Join-Path $Root "website"
if (-not (Test-Path $websiteDir)) {
    throw "website/ not found: $websiteDir"
}

function Copy-WebsiteToStaging {
    param([string]$Dest)
    New-Item -ItemType Directory -Path $Dest -Force | Out-Null
    Get-ChildItem -LiteralPath $websiteDir -Force | ForEach-Object {
        if ($_.Name -in @(".vercel", ".gitignore")) { return }
        $target = Join-Path $Dest $_.Name
        if ($_.PSIsContainer) {
            Copy-Item -LiteralPath $_.FullName -Destination $target -Recurse -Force
        } else {
            Copy-Item -LiteralPath $_.FullName -Destination $target -Force
        }
    }
}

if (-not $SkipPush) {
    Write-Host "=== Push website/ to gitee:$Branch ===" -ForegroundColor Cyan
    $staging = Join-Path $env:TEMP ("friday-gitee-pages-{0}" -f ([guid]::NewGuid().ToString("n")))
    $prevEap = $ErrorActionPreference
    try {
        Copy-WebsiteToStaging -Dest $staging
        Push-Location $staging
        $ErrorActionPreference = "Continue"
        git init -q | Out-Null
        git config user.email "friday-deploy@local" | Out-Null
        git config user.name "Friday Deploy" | Out-Null
        git checkout -B $Branch | Out-Null
        git add -A | Out-Null
        $status = git status --porcelain
        if (-not $status) {
            Write-Host "No website changes to publish." -ForegroundColor Yellow
        } else {
            $stamp = Get-Date -Format "yyyy-MM-dd HH:mm"
            git commit -m "chore: gitee pages deploy $stamp" -q
        }
        $remote = "https://oauth2:$GiteeToken@gitee.com/$GiteeUser/$RepoName.git"
        git push --force $remote "HEAD:$Branch" 2>&1 | ForEach-Object { Write-Host $_ }
        if ($LASTEXITCODE -ne 0) { throw "git push gitee $Branch failed (exit $LASTEXITCODE)" }
        Write-Host "Pushed to gitee:$Branch" -ForegroundColor Green
    } finally {
        $ErrorActionPreference = $prevEap
        Pop-Location
        Remove-Item -LiteralPath $staging -Recurse -Force -ErrorAction SilentlyContinue
    }
} else {
    Write-Host "Skip push to gitee:$Branch" -ForegroundColor Yellow
}

if (-not $SkipBuild) {
    Write-Host "=== Trigger Gitee Pages build ===" -ForegroundColor Cyan
    $Python = Join-Path $Root ".python-env\Scripts\python.exe"
    if (-not (Test-Path -LiteralPath $Python)) {
        $Python = Join-Path $Root ".venv\Scripts\python.exe"
    }
    if (-not (Test-Path -LiteralPath $Python)) { $Python = "python" }
    & $Python (Join-Path $Root "scripts\deploy_gitee_pages.py") --repo "$GiteeUser/$RepoName"
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
} else {
    Write-Host "Skip Gitee Pages build trigger." -ForegroundColor Yellow
}

$pagesHome = "https://$GiteeUser.gitee.io/$RepoName"
Write-Host ""
Write-Host "Gitee Pages mirror: $pagesHome" -ForegroundColor Green
Write-Host "First time? Enable Pages at https://gitee.com/$GiteeUser/$RepoName/pages (branch: $Branch)." -ForegroundColor Yellow
