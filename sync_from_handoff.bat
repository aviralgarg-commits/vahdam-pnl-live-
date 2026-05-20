@echo off
REM Daily 3:30 PM IST -- pull pnl_daily from the Cowork-refreshed handoff
REM folder, rebuild HTML, push to GitHub (Vercel auto-deploys).
REM
REM Skips when the handoff file is older than today (Cowork run failed).

cd /d "%~dp0"
if not exist logs mkdir logs

set PYTHONIOENCODING=utf-8

echo. >> logs\sync_from_handoff.log
echo ================================================================ >> logs\sync_from_handoff.log
echo [%DATE% %TIME%] sync_from_handoff.bat starting >> logs\sync_from_handoff.log
echo ================================================================ >> logs\sync_from_handoff.log

"%~dp0venv\Scripts\python.exe" "%~dp0scripts\sync_from_handoff.py" >> logs\sync_from_handoff.log 2>&1
set EXITCODE=%ERRORLEVEL%

echo [%DATE% %TIME%] sync_from_handoff.bat exit code %EXITCODE% >> logs\sync_from_handoff.log
exit /b %EXITCODE%
