@echo off
REM Local dev on Windows: frees this project's ports, then starts the backend and frontend in their own windows.
REM Double-click this file, or run it from any terminal.
echo Freeing ports 8000 and 5173 ...
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\free-ports.ps1" 8000 5173
timeout /t 2 /nobreak >nul
start "Rental checker backend :8000" cmd /k "cd /d %~dp0backend && call .venv\Scripts\activate.bat && uvicorn app.main:app --port 8000 --env-file .env"
start "Rental checker frontend :5173" cmd /k "cd /d %~dp0frontend && npm run dev -- --port 5173 --strictPort"
echo Started. Backend: http://localhost:8000/docs   App: http://localhost:5173
