@echo off
REM ==============================================================================
REM One-Click Launcher for Spotify -> YouTube Music Sync (Windows)
REM ==============================================================================
setlocal enabledelayedexpansion

cd /d "%~dp0"

echo ============================================================
echo    Spotify -^> YouTube Music Sync Launcher (Windows)
echo ============================================================

REM 1. Check Python
where python >nul 2>nul
if %ERRORLEVEL% neq 0 (
    echo [X] Error: Python is not installed or not in PATH.
    echo     Please install Python 3.10+ from https://www.python.org/
    pause
    exit /b 1
)

REM 2. Create and Activate Virtual Environment
if not exist "venv" (
    echo [*] Creating virtual environment in .\venv...
    python -m venv venv
    if %ERRORLEVEL% neq 0 (
        echo [X] Failed to create virtual environment.
        pause
        exit /b 1
    )
)

call venv\Scripts\activate.bat

REM 3. Install Dependencies
python -c "import fastapi, uvicorn, ytmusicapi" >nul 2>nul
if %ERRORLEVEL% neq 0 (
    echo [*] Installing required packages from requirements.txt...
    python -m pip install --upgrade pip --quiet
    pip install -r requirements.txt --quiet
    echo [v] Packages installed.
)

REM 4. Check Credentials & Environment
if not exist "backend\.env" if not exist ".env" (
    echo.
    echo [*] No credentials found. Starting Setup Wizard...
    python -m backend.setup_wizard
)

REM 5. Launch Application
set HOST=127.0.0.1
set PORT=8000
set URL=http://%HOST%:%PORT%

echo.
echo [v] Launching web server at %URL%...
echo     Press Ctrl+C to terminate.
echo ============================================================

start "" "%URL%"
uvicorn backend.main:app --host %HOST% --port %PORT%

pause
