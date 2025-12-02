@echo off
setlocal

:: Define the user data directory (User provided)
set "USER_DATA_DIR=C:\ChromeAutomationProfile"

:: Create the directory if it doesn't exist
if not exist "%USER_DATA_DIR%" mkdir "%USER_DATA_DIR%"

echo Starting Chrome for LinkedIn Agent...
echo User Data Directory: %USER_DATA_DIR%
echo Debugging Port: 9222
echo.
echo IMPORTANT: 
echo 1. If this is your first time running this script, you will need to LOG IN to LinkedIn in the opened window.
echo 2. Your login will be saved in this 'user_data' folder for next time.
echo 3. You do NOT need to close your main Chrome browser.
echo.

:: Try to find Chrome in standard locations
if exist "C:\Program Files\Google\Chrome\Application\chrome.exe" (
    set "CHROME_PATH=C:\Program Files\Google\Chrome\Application\chrome.exe"
) else if exist "C:\Program Files (x86)\Google\Chrome\Application\chrome.exe" (
    set "CHROME_PATH=C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"
) else (
    :: Fallback to hoping it's in PATH
    set "CHROME_PATH=chrome.exe"
)

start "" "%CHROME_PATH%" --remote-debugging-port=9222 --user-data-dir="%USER_DATA_DIR%"

echo Chrome launched. Please log in if needed, then let the agent continue.
pause
