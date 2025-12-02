@echo off
set "TASK_NAME=LinkedInAgentAuto"
set "SCRIPT_PATH=C:\Users\daars\.gemini\antigravity\scratch\linkedin_outreach_agent\run_agent_background.bat"

echo Creating Scheduled Task: %TASK_NAME%
echo Script: %SCRIPT_PATH%
echo Schedule: Daily, 5:00 PM - 11:00 PM, Every 1 Hour

schtasks /create /tn "%TASK_NAME%" /tr "\"%SCRIPT_PATH%\"" /sc daily /st 17:00 /ri 60 /du 06:00 /k /f

if %errorlevel% equ 0 (
    echo Task created successfully!
    echo You can view it in Windows Task Scheduler.
) else (
    echo Failed to create task. Please run as Administrator.
)
pause
