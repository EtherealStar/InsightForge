@echo off
chcp 65001 >nul

echo ========================================================
echo Starting Logos Development Environment...
echo ========================================================

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