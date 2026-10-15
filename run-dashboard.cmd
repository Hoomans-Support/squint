@echo off
rem Double-click to start the dashboard and open it in your browser.
rem Close this window to stop the server.
cd /d "%~dp0"
title Squint dashboard
start "" /b cmd /c "timeout /t 2 /nobreak >nul & start http://127.0.0.1:8080/"
".venv\Scripts\python.exe" app\server.py
pause
