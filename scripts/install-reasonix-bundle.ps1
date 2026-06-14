$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$BundleRoot = Join-Path $ProjectRoot "docs\reasonix"
$CursorRules = Join-Path $ProjectRoot ".cursor\rules"
$CursorSkills = Join-Path $ProjectRoot ".cursor\skills"

Write-Host "Friday Reasonix bundle install" -ForegroundColor Cyan
Write-Host "Project root: $ProjectRoot"
Write-Host "Canonical source: .cursor/rules + .cursor/skills" -ForegroundColor DarkGray

$RxSkills = Join-Path $ProjectRoot ".reasonix\skills"
$RxRules = Join-Path $ProjectRoot ".reasonix\rules"
$RxScripts = Join-Path $ProjectRoot ".reasonix\scripts"
New-Item -ItemType Directory -Force -Path $RxSkills, $RxRules, $RxScripts, (Join-Path $BundleRoot "skills"), (Join-Path $BundleRoot "rules") | Out-Null

if (Test-Path -LiteralPath $CursorRules) {
    Copy-Item -Path "$CursorRules\*" -Destination (Join-Path $BundleRoot "rules") -Recurse -Force
    Write-Host "  OK .cursor/rules -> docs/reasonix/rules" -ForegroundColor Green
} else {
    Write-Host "  skip .cursor/rules (missing)" -ForegroundColor DarkYellow
}
if (Test-Path -LiteralPath $CursorSkills) {
    Copy-Item -Path "$CursorSkills\*" -Destination (Join-Path $BundleRoot "skills") -Recurse -Force
    Write-Host "  OK .cursor/skills -> docs/reasonix/skills" -ForegroundColor Green
} else {
    Write-Host "  skip .cursor/skills (missing)" -ForegroundColor DarkYellow
}
Copy-Item -Path (Join-Path $BundleRoot "skills\*") -Destination $RxSkills -Force -ErrorAction SilentlyContinue
Copy-Item -Path (Join-Path $BundleRoot "rules\*") -Destination $RxRules -Force -ErrorAction SilentlyContinue
Write-Host "  OK .reasonix/skills + rules" -ForegroundColor Green

$ReasonixWorkspace = $env:REASONIX_WORKSPACE
if (-not $ReasonixWorkspace) {
    $ReasonixWorkspace = Join-Path "E:" "reasonix\workspace"
}
if ($ReasonixWorkspace -and (Test-Path -LiteralPath $ReasonixWorkspace)) {
    $RxWs = Join-Path $ReasonixWorkspace ".reasonix"
    New-Item -ItemType Directory -Force -Path (Join-Path $RxWs "skills"), (Join-Path $RxWs "rules") | Out-Null
    Copy-Item -Path (Join-Path $BundleRoot "skills\*") -Destination (Join-Path $RxWs "skills") -Force
    Copy-Item -Path (Join-Path $BundleRoot "rules\*") -Destination (Join-Path $RxWs "rules") -Force
    if (Test-Path -LiteralPath $RxScripts) {
        $dstScripts = Join-Path $RxWs "scripts"
        New-Item -ItemType Directory -Force -Path $dstScripts | Out-Null
        Copy-Item -Path "$RxScripts\*" -Destination $dstScripts -Force -ErrorAction SilentlyContinue
    }
    Write-Host "  OK $ReasonixWorkspace\.reasonix" -ForegroundColor Green
}

Write-Host ""
Write-Host "Done. Read:" -ForegroundColor Yellow
Write-Host "  docs\reasonix\INSTALL.md"
Write-Host "  docs\reasonix\user-rules.md  (paste into Reasonix user rules)"
Write-Host "  Edit rules/skills in .cursor\ only; re-run this script to sync."
