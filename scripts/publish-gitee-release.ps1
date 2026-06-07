param(
    [string]$GiteeUser = "Bxxxboo",
    [string]$RepoName = "friday",
    [string]$GiteeToken = $env:GITEE_TOKEN,
    [switch]$SkipBuild
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

function Upload-GiteeAsset {
    param([string]$ReleaseId, [string]$ZipPath, [string]$FileName)
    $Boundary = [System.Guid]::NewGuid().ToString()
    $FileEnc = [System.Text.Encoding]::GetEncoding("iso-8859-1").GetString([IO.File]::ReadAllBytes($ZipPath))
    $LF = "`r`n"
    $BodyLines = (
        "--$Boundary",
        "Content-Disposition: form-data; name=`"access_token`"$LF",
        $GiteeToken,
        "--$Boundary",
        "Content-Disposition: form-data; name=`"file`"; filename=`"$FileName`"",
        "Content-Type: application/zip$LF",
        $FileEnc,
        "--$Boundary--$LF"
    ) -join $LF
    $UploadUri = "https://gitee.com/api/v5/repos/$Repo/releases/$ReleaseId/attach_files"
    Invoke-RestMethod -Method Post -Uri $UploadUri -ContentType "multipart/form-data; boundary=$Boundary" -Body $BodyLines | Out-Null
}

if (-not $GiteeToken) {
    throw "Set GITEE_TOKEN first. Create at https://gitee.com/profile/personal_access_tokens"
}

$VersionLine = Select-String -Path "friday\version.py" -Pattern '__version__ = "(.+)"' | Select-Object -First 1
if (-not $VersionLine) { throw "Cannot read version" }
$Version = $VersionLine.Matches[0].Groups[1].Value
$Tag = "v$Version"
$Repo = "$GiteeUser/$RepoName"

if (-not $SkipBuild) {
    powershell -ExecutionPolicy Bypass -File scripts\make-release.ps1
}

$Zip = Join-Path $PWD "release\Friday-Windows.zip"
if (-not (Test-Path $Zip)) {
    $Zip = (Get-ChildItem (Join-Path $PWD "release") -Filter "*-Windows.zip" | Select-Object -First 1).FullName
}
if (-not $Zip) { throw "Release zip not found. Run scripts/make-release.ps1 first." }

$ReleaseNotes = & (Join-Path $Root "scripts\release-notes.ps1") | Out-String
$ReleaseNotes = $ReleaseNotes.Trim()

$ReleaseId = $null
$TagEncoded = [Uri]::EscapeDataString($Tag)
foreach ($lookupUri in @(
    "https://gitee.com/api/v5/repos/$Repo/releases/tags/$TagEncoded",
    "https://gitee.com/api/v5/repos/$Repo/releases/tags/$TagEncoded?access_token=$GiteeToken"
)) {
    try {
        $existing = Invoke-RestMethod -Uri $lookupUri
        if ($existing -and $existing.id) {
            $ReleaseId = $existing.id
            Write-Host "Gitee release $Tag exists (id $ReleaseId), uploading asset ..." -ForegroundColor Yellow
            break
        }
    } catch {
        continue
    }
}
if (-not $ReleaseId) {
    Write-Host "Creating Gitee release $Tag on $Repo ..." -ForegroundColor Cyan
    $Body = @{
        access_token = $GiteeToken
        tag_name = $Tag
        name = "星期五 v$Version"
        body = $ReleaseNotes
        target_commitish = "main"
    }
    $Release = Invoke-RestMethod -Method Post -Uri "https://gitee.com/api/v5/repos/$Repo/releases" -Body $Body
    $ReleaseId = $Release.id
}
if (-not $ReleaseId) { throw "Failed to resolve Gitee release id for $Tag" }

Write-Host "Uploading Friday-Windows.zip ($([math]::Round((Get-Item $Zip).Length / 1MB, 1)) MB) ..." -ForegroundColor Cyan
Upload-GiteeAsset -ReleaseId $ReleaseId -ZipPath $Zip -FileName "Friday-Windows.zip"

Write-Host ""
Write-Host "Gitee release done!" -ForegroundColor Green
Write-Host "  https://gitee.com/$Repo/releases/tag/$Tag"
