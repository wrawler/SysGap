@echo off
setlocal
cd /d "%~dp0"
title SysGap - Hardware Assessment
color 0B
cls

echo.
echo  ================================================================
echo                           S Y S G A P
echo          HARDWARE ASSESSMENT  ^|  COMPONENT DECISION
echo  ================================================================
echo.

where python >nul 2>&1
if errorlevel 1 (
    echo  [ERROR] Python was not found on PATH.
    echo  Install Python 3.10 or newer, enable "Add Python to PATH",
    echo  then start SysGap.bat again.
    echo.
    pause
    exit /b 1
)

python -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)" >nul 2>&1
if errorlevel 1 (
    echo  [ERROR] Python 3.10 or newer is required.
    echo.
    pause
    exit /b 1
)

if not exist ".venv\Scripts\python.exe" (
    echo  [SETUP] Creating an isolated Python environment...
    python -m venv .venv
    if errorlevel 1 (
        echo  [ERROR] Could not create the Python environment.
        echo.
        pause
        exit /b 1
    )
)

if not exist ".venv\.sysgap-dependencies-installed" (
    echo  [SETUP] Installing client requirements. Internet is needed
    echo          during this first-time setup.
    ".venv\Scripts\python.exe" -m pip install -r requirements.txt
    if errorlevel 1 (
        echo.
        echo  [ERROR] Dependency installation failed. Check Python and
        echo          your internet connection, then try again.
        echo.
        pause
        exit /b 1
    )
    type nul > ".venv\.sysgap-dependencies-installed"
)

echo.
".venv\Scripts\python.exe" cli.py run %*
set "RESULT=%ERRORLEVEL%"
echo.
if not "%RESULT%"=="0" (
    echo  [ERROR] SysGap stopped with exit code %RESULT%.
    echo  See the details above. Any local assessment remains in reports.
) else (
    echo  [DONE] SysGap assessment flow completed.
)
echo.
pause
exit /b %RESULT%
