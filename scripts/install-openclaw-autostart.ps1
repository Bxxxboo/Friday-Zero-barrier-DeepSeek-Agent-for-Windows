# OpenClaw Gateway autostart (silent, no CMD window)
# Install:  powershell -ExecutionPolicy Bypass -File scripts\install-openclaw-autostart.ps1
# Remove:   powershell -ExecutionPolicy Bypass -File scripts\install-openclaw-autostart.ps1 -Remove
# Startup folder only: install-openclaw-autostart.ps1 -StartupFolder

param(
    [switch]$Remove,
    [switch]$StartupFolder,
    [int]$BootDelaySec = 30
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$TaskName = "Friday OpenClaw Gateway"
$StartupVbsName = "Friday-OpenClaw-Gateway.vbs"

function Get-GatewayCmdPath {
    $path = Join-Path $env:USERPROFILE '.openclaw\gateway.cmd'
    if (-not (Test-Path -LiteralPath $path)) {
        throw "gateway.cmd not found: $path (configure WeChat bridge in Friday first)"
    }
    return $path
}

function Get-StartupFolder {
    return [Environment]::GetFolderPath('Startup')
}

function Format-Delay([int]$sec) {
    $m = [int][math]::Floor($sec / 60)
    $s = [int]($sec % 60)
    return $m.ToString('0000') + ':' + $s.ToString('00')
}

function Write-HiddenVbs([string]$targetPath, [string]$gatewayCmd) {
    $line2 = 'sh.Run "cmd /c ""{0}""", 0, False' -f $gatewayCmd
    $content = "Set sh = CreateObject(""WScript.Shell"")`r`n$line2`r`n"
    [System.IO.File]::WriteAllText($targetPath, $content, [System.Text.Encoding]::Unicode)
}

function Get-LaunchSpec {
    $gatewayCmd = Get-GatewayCmdPath
    $repoVbs = Join-Path $Root 'scripts\openclaw-gateway-hidden.vbs'
    Write-HiddenVbs $repoVbs $gatewayCmd
    return @{
        GatewayCmd = $gatewayCmd
        TaskRun    = ('wscript.exe "{0}"' -f $repoVbs)
        Mode       = 'hidden VBS + %USERPROFILE%\.openclaw\gateway.cmd'
    }
}

function Install-StartupFolder([hashtable]$spec) {
    $vbsPath = Join-Path (Get-StartupFolder) $StartupVbsName
    Write-HiddenVbs $vbsPath $spec.GatewayCmd
    return $vbsPath
}

function Remove-Autostart {
    schtasks /Delete /TN $TaskName /F 2>$null | Out-Null
    $vbsPath = Join-Path (Get-StartupFolder) $StartupVbsName
    if (Test-Path -LiteralPath $vbsPath) {
        Remove-Item -LiteralPath $vbsPath -Force
        Write-Host "Removed: $vbsPath"
    }
    Write-Host "Removed autostart entries"
}

if ($Remove) {
    Remove-Autostart
    exit 0
}

$spec = Get-LaunchSpec

if ($StartupFolder) {
    $vbs = Install-StartupFolder $spec
    Write-Host "Mode: $($spec.Mode)"
    Write-Host "Installed: $vbs"
    Write-Host "Test: double-click the VBS or reboot after logon"
    exit 0
}

Write-Host "Mode: $($spec.Mode)"
$delay = Format-Delay $BootDelaySec
$createOut = schtasks /Create /TN $TaskName /TR $spec.TaskRun /SC ONLOGON /DELAY $delay /RL LIMITED /F 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Host "schtasks failed: $($createOut -join ' ')"
    Write-Host "Falling back to Startup folder..."
    $vbs = Install-StartupFolder $spec
    Write-Host "Installed: $vbs"
    exit 0
}

Write-Host ""
Write-Host "Created scheduled task: $TaskName"
Write-Host "  Trigger: ${BootDelaySec}s after logon"
Write-Host "  Test: schtasks /Run /TN `"$TaskName`""
Write-Host "  Remove: install-openclaw-autostart.ps1 -Remove"
