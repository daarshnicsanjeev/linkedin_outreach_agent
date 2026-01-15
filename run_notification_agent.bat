@echo off
echo ============================================
echo LinkedIn Master Run Script
echo ============================================
echo.

cd /d "%~dp0"

set ERROR_FLAG=0

echo [STEP 1/2] Growing Network (Sending Invites)...
python notification_agent.py
if %errorlevel% neq 0 (
    echo ERROR: notification_agent.py failed with exit code %errorlevel%
    set ERROR_FLAG=1
)
echo.

echo [STEP 2/2] Engaging (Liking Comments)...
python engagement_agent.py
if %errorlevel% neq 0 (
    echo ERROR: engagement_agent.py failed with exit code %errorlevel%
    set ERROR_FLAG=1
)

echo.

if %ERROR_FLAG% equ 1 (
    echo.
    echo *** ERRORS OCCURRED - Press any key to close ***
    pause > nul
) else (
    echo All tasks finished successfully.
)
