@echo off
REM ============================================================
REM gen_db_docs.bat — 一键生成数据库文档
REM 用法: scripts\gen_db_docs.bat
REM ============================================================

cd /d "%~dp0.."

REM 从 .env 加载 PG_DSN
for /f "usebackq tokens=1,* delims==" %%a in (".env") do (
    if "%%a"=="PG_DSN" set PG_DSN=%%b
)

if "%PG_DSN%"=="" (
    echo 错误: 未在 .env 中找到 PG_DSN
    exit /b 1
)

echo [tbls] 使用 DSN: %PG_DSN%
echo [tbls] 生成数据库文档...
tbls doc --force

if %ERRORLEVEL% equ 0 (
    echo [tbls] ✓ 文档生成完成! 查看 docs/generated/dbdoc/
) else (
    echo [tbls] ✗ 文档生成失败
    exit /b 1
)

echo [tbls] 运行 lint 检查...
tbls lint

echo.
echo 完成!
