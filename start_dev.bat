@echo off
chcp 65001 >nul

echo ========================================================
echo Starting Logos Development Environment...
echo ========================================================

:: Clean up orphaned processes from previous runs
echo Cleaning up existing service processes...
powershell -NoProfile -Command "$ports = @(5173, 8000, 5555); foreach ($p in $ports) { Get-NetTCPConnection -LocalPort $p -State Listen -ErrorAction SilentlyContinue | ForEach-Object { Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue } }"
powershell -NoProfile -Command "Get-CimInstance Win32_Process -Filter \"Name='python.exe' or Name='celery.exe' or Name='node.exe'\" | Where-Object { $_.CommandLine -match 'delivery\.server' -or $_.CommandLine -match 'celery_app' } | Invoke-CimMethod -MethodName Terminate | Out-Null"
echo Cleanup finished.
echo.

:: Set Python path so all modules can be found
set PYTHONPATH=D:\study\Logos

:: Start infrastructure via Docker Compose
echo Starting infrastructure (PostgreSQL + pgvector, Redis)...
docker compose up -d
echo.
echo Infrastructure is running.

echo.
echo ========================================================
echo Starting all services via Honcho...
echo.
echo Access URLs:
echo - Frontend: http://localhost:5173
echo - Backend API: http://localhost:8000
echo - Flower Dashboard: http://localhost:5555
echo.
echo To stop all services, simply press Ctrl+C in this terminal.
echo To stop infrastructure: docker compose down
echo ========================================================
echo.

honcho start