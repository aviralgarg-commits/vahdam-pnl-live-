@echo off
REM Vahdam P&L Live — Daily refresh
REM Triggered 2x daily by Task Scheduler: 15:30 IST (= 11:00 BST/London),
REM and 03:30 IST next day (= 15:00 PDT/Pacific).
REM Pulls Windsor.ai ads + tiktok_shop orders, re-ingests affiliate CSVs,
REM rebuilds dashboard HTML, logs to logs\refresh.log.

cd /d "%~dp0"
if not exist logs mkdir logs

set PYTHONIOENCODING=utf-8

echo. >> logs\refresh.log
echo ================================================================ >> logs\refresh.log
echo [%DATE% %TIME%] refresh_daily.bat starting >> logs\refresh.log
echo ================================================================ >> logs\refresh.log

"%~dp0venv\Scripts\python.exe" "%~dp0scripts\refresh_daily.py" >> logs\refresh.log 2>&1
set EXITCODE=%ERRORLEVEL%

REM On success, auto-commit the rebuilt dashboard + data so Vercel redeploys.
REM (Falls through silently on failure — log captures the error.)
if %EXITCODE%==0 (
    echo [%DATE% %TIME%] Auto-commit and push to GitHub >> logs\refresh.log
    git add public/index.html data/pnl_daily.json data/windsor_ads_daily.json data/windsor_ads_30d.json data/windsor_shop_orders_daily.json >> logs\refresh.log 2>&1
    git diff --cached --quiet
    if errorlevel 1 (
        git commit -m "chore: scheduled refresh %DATE% %TIME%" >> logs\refresh.log 2>&1
        git push vahdam-pnl-live- main >> logs\refresh.log 2>&1
        echo [%DATE% %TIME%] Pushed to GitHub — Vercel will redeploy >> logs\refresh.log
    ) else (
        echo [%DATE% %TIME%] No dashboard changes to commit >> logs\refresh.log
    )
)

echo [%DATE% %TIME%] refresh_daily.bat exit code %EXITCODE% >> logs\refresh.log
exit /b %EXITCODE%
