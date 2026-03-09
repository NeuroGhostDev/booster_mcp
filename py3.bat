@echo off
REM Запуск Booster MCP сервера через py launcher (Python 3.11)
cd /d "%~dp0"
py -3.11 server.py %*
