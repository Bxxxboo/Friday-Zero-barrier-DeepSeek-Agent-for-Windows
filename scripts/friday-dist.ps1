$ErrorActionPreference = "Stop"

function Get-FridayDistDir {
    param([string]$Root)
    $ascii = Join-Path (Join-Path $Root "dist") "Friday"
    if (Test-Path $ascii) { return $ascii }
    $legacy = Join-Path (Join-Path $Root "dist") (-join ([char]0x661F, [char]0x671F, [char]0x4E94))
    if (Test-Path $legacy) { return $legacy }
    return $ascii
}

function Get-FridayExe {
    param([string]$DistDir)
    $exe = Get-ChildItem $DistDir -Filter "*.exe" -ErrorAction SilentlyContinue | Select-Object -First 1
    return $exe
}
