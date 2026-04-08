@echo off
:: ============================================
:: ONE-TIME SETUP - Run this as Administrator
:: Sets up:
::   1. WatchTower auto-start on Windows login
::   2. Daily 6 AM repo update
:: ============================================

echo.
echo ========================================
echo   Alchemy Scheduled Tasks Setup
echo   Run this as Administrator!
echo ========================================
echo.

:: ----------------------------------------
:: Task 1: WatchTower auto-start on login
:: ----------------------------------------
echo [1/2] Creating WatchTower auto-start task...

schtasks /create /tn "Alchemy\WatchTower AutoStart" ^
    /tr "C:\Users\joshu\Repos\Alchemy-Protocols\start-watchtower.bat" ^
    /sc onlogon ^
    /rl highest ^
    /f

if %ERRORLEVEL% EQU 0 (
    echo       WatchTower will now auto-start when you log in.
) else (
    echo       FAILED - Make sure you're running as Administrator.
)

echo.

:: ----------------------------------------
:: Task 2: Daily 6 AM repo update
:: ----------------------------------------
echo [2/2] Creating daily 6 AM repo update task...

schtasks /create /tn "Alchemy\Daily Repo Update" ^
    /tr "C:\Users\joshu\Repos\Alchemy-Protocols\update-all-repos.bat" ^
    /sc daily ^
    /st 06:00 ^
    /rl highest ^
    /f

if %ERRORLEVEL% EQU 0 (
    echo       Repos will update daily at 6:00 AM.
) else (
    echo       FAILED - Make sure you're running as Administrator.
)

echo.
echo ========================================
echo   Setup complete!
echo.
echo   To verify, open Task Scheduler and
echo   look under the "Alchemy" folder.
echo.
echo   To remove later:
echo     schtasks /delete /tn "Alchemy\WatchTower AutoStart" /f
echo     schtasks /delete /tn "Alchemy\Daily Repo Update" /f
echo ========================================
echo.
pause
