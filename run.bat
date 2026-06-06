@echo off
REM MyAgent Windows Startup Script
REM Auto-detects Python from conda env or system PATH
REM Equivalent to run.sh on Linux

setlocal EnableDelayedExpansion

REM Switch to script directory
cd /d "%~dp0"

REM Detect Python path (prefer conda environment)
set "PYTHON="

if defined CONDA_PREFIX (
    set "PYTHON=!CONDA_PREFIX!\python.exe"
    if exist "!PYTHON!" goto :found
)

if exist "%USERPROFILE%\miniconda3\envs\myagent\python.exe" (
    set "PYTHON=%USERPROFILE%\miniconda3\envs\myagent\python.exe"
    goto :found
)

if exist "%USERPROFILE%\anaconda3\envs\myagent\python.exe" (
    set "PYTHON=%USERPROFILE%\anaconda3\envs\myagent\python.exe"
    goto :found
)

REM Fallback to system Python in PATH
where python >nul 2>&1
if %errorlevel%==0 (
    set "PYTHON=python"
    goto :found
)

echo Error: Python not found. Install Miniconda or add python to PATH.
exit /b 1

:found
REM Parse subcommand (default: cli)
set "CMD=%~1"
if "%CMD%"=="" set "CMD=cli"

if "%CMD%"=="cli" (
    "!PYTHON!" -m src.main cli %2 %3 %4 %5 %6 %7 %8 %9
) else if "%CMD%"=="gateway" (
    "!PYTHON!" -m src.main gateway %2 %3 %4 %5 %6 %7 %8 %9
) else if "%CMD%"=="status" (
    "!PYTHON!" -m src.main status %2 %3 %4 %5 %6 %7 %8 %9
) else if "%CMD%"=="tools" (
    "!PYTHON!" -m src.main tools %2 %3 %4 %5 %6 %7 %8 %9
) else if "%CMD%"=="skills" (
    "!PYTHON!" -m src.main skills %2 %3 %4 %5 %6 %7 %8 %9
) else (
    "!PYTHON!" -m src.main %*
)

endlocal
