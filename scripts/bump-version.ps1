param(
    [ValidateSet("patch", "minor", "major")]
    [string]$Part = "patch",
    [string]$Set = ""
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$VersionPy = Join-Path $Root "friday\version.py"
$VersionInfo = Join-Path $Root "scripts\version_info.py"

if (-not (Test-Path $VersionPy)) { throw "Missing $VersionPy" }

$content = Get-Content $VersionPy -Raw -Encoding UTF8
if ($content -notmatch '__version__ = "(\d+)\.(\d+)\.(\d+)"') {
    throw "Cannot parse __version__ in friday/version.py"
}

$major = [int]$Matches[1]
$minor = [int]$Matches[2]
$patch = [int]$Matches[3]

if ($Set) {
    if ($Set -notmatch '^(\d+)\.(\d+)\.(\d+)$') {
        throw "Set must be semver like 1.2.3"
    }
    $major = [int]$Matches[1]
    $minor = [int]$Matches[2]
    $patch = [int]$Matches[3]
} else {
    switch ($Part) {
        "major" { $major++; $minor = 0; $patch = 0 }
        "minor" { $minor++; $patch = 0 }
        default { $patch++ }
    }
}

$newVersion = "$major.$minor.$patch"
$newTuple = "($major, $minor, $patch, 0)"
$fileVersion = "$newVersion.0"

$content = [regex]::Replace(
    $content,
    '__version__ = "\d+\.\d+\.\d+"',
    "__version__ = `"$newVersion`""
)
$content = [regex]::Replace(
    $content,
    '__version_tuple__ = \(\d+, \d+, \d+, \d+\)',
    "__version_tuple__ = $newTuple"
)
Set-Content -Path $VersionPy -Value ($content.TrimEnd() + "`n") -Encoding UTF8 -NoNewline

if (Test-Path $VersionInfo) {
    $info = Get-Content $VersionInfo -Raw -Encoding UTF8
    $info = [regex]::Replace($info, 'filevers=\(\d+, \d+, \d+, \d+\)', "filevers=$newTuple")
    $info = [regex]::Replace($info, 'prodvers=\(\d+, \d+, \d+, \d+\)', "prodvers=$newTuple")
    $info = [regex]::Replace($info, 'StringStruct\("FileVersion", "[^"]+"\)', "StringStruct(`"FileVersion`", `"$fileVersion`")")
    $info = [regex]::Replace($info, 'StringStruct\("ProductVersion", "[^"]+"\)', "StringStruct(`"ProductVersion`", `"$fileVersion`")")
    Set-Content -Path $VersionInfo -Value $info -Encoding UTF8 -NoNewline
}

Write-Host "Version bumped to $newVersion" -ForegroundColor Green
Write-Host "  friday/version.py"
if (Test-Path $VersionInfo) { Write-Host "  scripts/version_info.py" }
