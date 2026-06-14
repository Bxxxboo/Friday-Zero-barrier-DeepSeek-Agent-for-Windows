@echo off
setlocal
cd /d "%~dp0.."
python -m pip install -q ruff>=0.8.0
python -m ruff check friday tests
exit /b %ERRORLEVEL%
