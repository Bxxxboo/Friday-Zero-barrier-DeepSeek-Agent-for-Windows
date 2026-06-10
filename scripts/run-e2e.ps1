# Playwright UI E2E — 首次运行需下载 Chromium（约 300MB）
$ErrorActionPreference = "Stop"
Set-Location (Split-Path $PSScriptRoot -Parent)

pip install -r requirements-dev.txt -q
python -m playwright install chromium
python -m pytest tests/e2e -v @args
