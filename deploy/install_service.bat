@echo off
REM ============================================================
REM cewmail - Windows service installer (via NSSM)
REM
REM PREREQUISITES (do these once, manually, before running this script):
REM   1. Install Python 3.11+ on this machine.
REM   2. Install uv:  https://docs.astral.sh/uv/getting-started/installation/
REM        (or: pip install uv)
REM   3. From this project's root folder, run:
REM        uv sync
REM      This creates a .venv\ folder here with everything installed.
REM   4. Copy .env.example to .env (in the project root) and fill in real values:
REM      GEMINI_API_KEY, OPENAI_API_KEY, GMAIL_ADDRESS, GMAIL_APP_PASSWORD.
REM   5. Download nssm from https://nssm.cc/download and either:
REM        - put nssm.exe on your system PATH, or
REM        - put it at deploy\tools\nssm.exe (next to this script)
REM   6. Run THIS script from an elevated (Administrator) Command Prompt.
REM ============================================================

setlocal
set SERVICE_NAME=cewmail
set APP_DIR=%~dp0..
set VENV_PYTHON=%APP_DIR%\.venv\Scripts\python.exe
set APP_SCRIPT=%APP_DIR%\app.py

set NSSM=%~dp0tools\nssm.exe
if not exist "%NSSM%" set NSSM=nssm

if not exist "%VENV_PYTHON%" (
    echo ERROR: %VENV_PYTHON% not found. Run "uv sync" in "%APP_DIR%" first.
    exit /b 1
)
if not exist "%APP_DIR%\.env" (
    echo ERROR: %APP_DIR%\.env not found. Copy .env.example to .env and fill it in first.
    exit /b 1
)

if not exist "%APP_DIR%\logs" mkdir "%APP_DIR%\logs"

"%NSSM%" install %SERVICE_NAME% "%VENV_PYTHON%" "%APP_SCRIPT%"
"%NSSM%" set %SERVICE_NAME% AppDirectory "%APP_DIR%"
"%NSSM%" set %SERVICE_NAME% Start SERVICE_AUTO_START
"%NSSM%" set %SERVICE_NAME% AppStdout "%APP_DIR%\logs\service.out.log"
"%NSSM%" set %SERVICE_NAME% AppStderr "%APP_DIR%\logs\service.err.log"
"%NSSM%" set %SERVICE_NAME% AppRotateFiles 1

echo Service "%SERVICE_NAME%" installed. Starting it now...
"%NSSM%" start %SERVICE_NAME%

echo Done. Check status with: sc query %SERVICE_NAME%
echo The app should now be reachable at http://127.0.0.1:5000 on this machine.
endlocal
