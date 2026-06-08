# Friday desktop autostart (silent)
# Install:  powershell -ExecutionPolicy Bypass -File scripts\install-friday-autostart.ps1
# Remove:   powershell -ExecutionPolicy Bypass -File scripts\install-friday-autostart.ps1 -Remove

param([switch]$Remove)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$Python = Join-Path $Root ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $Python)) {
    $Python = "python"
}

$Flag = if ($Remove) { "False" } else { "True" }
& $Python -c "import json, sys; sys.path.insert(0, r'$Root'); from friday.autostart import set_autostart_enabled; print(json.dumps(set_autostart_enabled($Flag), ensure_ascii=False))"
