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

echo [%DATE% %TIME%] refresh_daily.bat exit code %EXITCODE% >> logs\refresh.log
exit /b %EXITCODE%
