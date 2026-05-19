@echo off
REM Vahdam P&L Live — Daily refresh.
REM Triggered 2x daily by Task Scheduler:
REM   VahdamPnL_MorningUK  @ 15:30 IST (= 11:00 Europe/London)
REM   VahdamPnL_EveningUS  @ 03:30 IST next day (= 15:00 America/Los_Angeles)
REM
REM Pipeline (in refresh_daily.py): scrape (orders/ads/affiliate/smart-promo)
REM -> aggregate_affiliate -> build_dashboard -> git push -> verify.

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
