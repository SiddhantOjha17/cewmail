@echo off
REM ============================================================
REM cewmail - update the deployed service from git and restart it.
REM
REM Requires: this checkout already has a git remote configured, e.g.
REM   git remote add origin <your-repo-url>
REM (set up once, manually, after cloning onto this Windows machine).
REM
REM MUST be run from an elevated (Administrator) Command Prompt --
REM restarting a Windows service always requires admin rights, the
REM same as the initial install. Running this unelevated fails with
REM "OpenService() is denied" on the final restart step.
REM ============================================================

setlocal
set SERVICE_NAME=cewmail
set APP_DIR=%~dp0..
set NSSM=%~dp0tools\nssm.exe
if not exist "%NSSM%" set NSSM=nssm

cd /d "%APP_DIR%"

git pull
if errorlevel 1 (
    echo git pull failed - aborting restart to avoid running against a broken pull.
    exit /b 1
)

uv sync
if errorlevel 1 (
    echo "uv sync" failed - aborting restart.
    exit /b 1
)

"%NSSM%" restart %SERVICE_NAME%
if errorlevel 1 (
    echo Restart failed - if you saw "OpenService() is denied", re-run this
    echo script from an elevated ^(Administrator^) Command Prompt.
    exit /b 1
)
echo Update complete, service restarted.
endlocal
