@echo off
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0sync-remotes.ps1" %*
