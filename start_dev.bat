@echo off
chcp 65001 >nul

echo ========================================================
echo Starting Logos Development Environment...
echo ========================================================

echo Cleaning up existing service processes...
powershell -NoProfile -Command "$ports = @(5173, 8005); foreach ($p in $ports) { Get-NetTCPConnection -LocalPort $p -State Listen -ErrorAction SilentlyContinue | ForEach-Object { Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue } }"
powershell -NoProfile -Command "Get-CimInstance Win32_Process -Filter \"Name='python.exe' or Name='celery.exe' or Name='node.exe'\" | Where-Object { $_.CommandLine -match 'delivery\.server' -or $_.CommandLine -match 'celery_app' } | Invoke-CimMethod -MethodName Terminate | Out-Null"
echo Cleanup finished.
echo.

set PYTHONPATH=D:\study\Logos

echo Starting infrastructure (PostgreSQL + Redis + Qdrant)...
docker compose up -d
echo.
echo Infrastructure is running.
echo.

echo Pre-initializing database schema to prevent deadlock...
call D:\study\Logos\.venv\Scripts\activate.bat

start /b "" D:\study\Logos\.venv\Scripts\python.exe -m delivery.server
echo Waiting for schema sync and lock release...
powershell -Command "Start-Sleep -Seconds 5"

powershell -NoProfile -Command "Get-NetTCPConnection -LocalPort 8005 -State Listen -ErrorAction SilentlyContinue | ForEach-Object { Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue }"
echo Pre-initialization finished. No deadlock risks detected.
echo.

echo ========================================================
echo Starting all services via Honcho...
echo.
echo Access URLs:
echo - Frontend: http://localhost:5173
echo - Backend API: http://localhost:8005
echo.
echo To stop all services, simply press Ctrl+C in this terminal.
echo To stop infrastructure: docker compose down
echo ========================================================
echo.

honcho start
