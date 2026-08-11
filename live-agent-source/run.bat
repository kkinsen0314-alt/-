@echo off
setlocal
chcp 65001 > nul
set PYTHONIOENCODING=utf-8

set AGENT_DIR=D:\Workspace\project002-live-agent
set PYTHON=C:\Users\Administrator\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe

if "%LLM_API_KEY%"=="" (
    echo [ERROR] 请先设置环境变量 LLM_API_KEY
    exit /b 1
)

if "%~1"=="" (
    echo ??: run.bat [Excel????] [??]
    echo ??: daily ^(??^) / anomaly / optimization / all
    echo ??: run.bat "C:\data\????.xlsx" all
    exit /b 1
)

set FILE=%~1
set MODE=daily
if not "%~2"=="" set MODE=%~2

echo ====================================
echo   ???????? Agent
echo   ??: %FILE%
echo   ??: %MODE%
echo ====================================
echo.

%PYTHON% -W ignore "%AGENT_DIR%\agent.py" "%FILE%" --mode %MODE% --api-key "%LLM_API_KEY%" --output "%AGENT_DIR%\output"

echo.
echo ??????: %AGENT_DIR%\output\
echo.
explorer "%AGENT_DIR%\output"
endlocal
