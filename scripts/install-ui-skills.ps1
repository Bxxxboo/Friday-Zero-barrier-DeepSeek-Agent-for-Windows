# 从 GitHub 下载 UI 设计相关 Agent Skills 到 .cursor/skills/
$ErrorActionPreference = "Stop"
Set-Location (Split-Path -Parent $PSScriptRoot)

$skillsRoot = Join-Path $PWD ".cursor\skills"
$tmp = Join-Path $env:TEMP "friday-skills-dl"
New-Item -ItemType Directory -Force -Path $skillsRoot, $tmp | Out-Null

function Get-ExtractedRoot($zipName) {
    $zip = Join-Path $tmp "$zipName.zip"
    $extractParent = Join-Path $tmp "extract-$zipName"
    if (Test-Path $extractParent) { Remove-Item $extractParent -Recurse -Force }
    New-Item -ItemType Directory -Force -Path $extractParent | Out-Null
    Expand-Archive -Path $zip -DestinationPath $extractParent -Force
    $folder = Get-ChildItem $extractParent -Directory | Select-Object -First 1
    if (-not $folder) { throw "No folder after extract: $zipName" }
    return $folder.FullName
}

function Download-Repo($repo, $zipName) {
    $zip = Join-Path $tmp "$zipName.zip"
    $url = "https://github.com/$repo/archive/refs/heads/main.zip"
    Write-Host "Downloading $repo ..."
    Invoke-WebRequest -Uri $url -OutFile $zip -UseBasicParsing
    return Get-ExtractedRoot $zipName
}

function Install-SkillDir($source, $destName) {
    if (-not (Test-Path $source)) { throw "Missing skill source: $source" }
    $dest = Join-Path $skillsRoot $destName
    if (Test-Path $dest) { Remove-Item $dest -Recurse -Force }
    Copy-Item $source $dest -Recurse -Force
    Write-Host "  -> .cursor/skills/$destName"
}

# 1 Impeccable
$imp = Download-Repo "pbakaus/impeccable" "impeccable"
Install-SkillDir (Join-Path $imp ".cursor\skills\impeccable") "impeccable"

# 2 Taste Skill (default v2)
$taste = Download-Repo "Leonxlnx/taste-skill" "taste-skill"
Install-SkillDir (Join-Path $taste "skills\taste-skill") "design-taste-frontend"

# 3 UI Design Brain
$brain = Download-Repo "carmahhawwari/ui-design-brain" "ui-design-brain"
Install-SkillDir $brain "ui-design-brain"

# 4 Motion — micro-interactions + motion.dev patterns
$micro = Download-Repo "solinkz/micro-interactions-skill" "micro-interactions"
$microInner = Join-Path $micro "skills\micro-interactions"
if (Test-Path $microInner) {
    Install-SkillDir $microInner "micro-interactions"
} else {
    Install-SkillDir $micro "micro-interactions"
}
$motion = Download-Repo "199-biotechnologies/motion-dev-animations-skill" "motion-dev"
Install-SkillDir $motion "motion-dev-animations"

# 5 Better Icons
$icons = Download-Repo "better-auth/better-icons" "better-icons"
New-Item -ItemType Directory -Force -Path (Join-Path $skillsRoot "better-icons") | Out-Null
Copy-Item (Join-Path $icons "skills\SKILL.md") (Join-Path $skillsRoot "better-icons\SKILL.md") -Force
Write-Host "  -> .cursor/skills/better-icons"

Write-Host ""
Write-Host "Skills installed under .cursor/skills/" -ForegroundColor Green
Get-ChildItem $skillsRoot -Directory | ForEach-Object { Write-Host "  - $($_.Name)" }
