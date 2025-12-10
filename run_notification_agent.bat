@echo off
echo ============================================
echo LinkedIn Notification Engagement Agent
echo ============================================
echo.

cd /d "%~dp0"

echo Starting agent...
python notification_agent.py

echo.
echo Agent finished. Press any key to close.
pause > nul
