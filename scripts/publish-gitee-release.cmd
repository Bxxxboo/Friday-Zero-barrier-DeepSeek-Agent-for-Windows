@echo off
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0publish-gitee-release.ps1" %*
