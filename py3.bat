@echo off
REM Start Booster MCP through the project environment.
cd /d "%~dp0"
if exist "%~dp0.venv\Scripts\python.exe" goto run_venv

where uv >nul 2>nul
if errorlevel 1 goto missing_environment
uv run python server.py %*
exit /b %ERRORLEVEL%

:run_venv
"%~dp0.venv\Scripts\python.exe" "%~dp0server.py" %*
exit /b %ERRORLEVEL%

:missing_environment
echo Booster environment was not found. Run "uv sync --extra dev" first.
exit /b 1
