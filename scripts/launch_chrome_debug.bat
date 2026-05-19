@echo off
REM Launches a SIDE Chrome profile with remote debugging enabled.
REM
REM Why a side profile (not the default one):
REM   Chrome 136+ silently disables --remote-debugging-port whenever the
REM   active profile is signed in to a Google Account (cookie-theft mitigation,
REM   ref: https://groups.google.com/a/chromium.org/g/headless-dev — "We
REM   disabled remote debugging when Sync is signed in"). That breaks the
REM   default-profile approach entirely; the flag silently no-ops.
REM
REM   The side profile is NOT signed into Chrome sync, so debug works. You
REM   log into TikTok Seller Center *inside the web page* via Google SSO
REM   popup — that's web-level OAuth, not Chrome-account login, so the
REM   restriction doesn't apply.
REM
REM One-time setup (per machine):
REM   1. Double-click this bat. A fresh Chrome window opens at
REM      seller-uk.tiktok.com/homepage in a brand-new profile.
REM   2. Log in via Google SSO. Repeat for seller-us.tiktok.com/homepage
REM      in a new tab.
REM   3. Close the window. Re-run the bat — you should NOT have to log in
REM      again. Cookies persisted in the side-profile dir.
REM
REM   Daily: just leave this Chrome window running. Scrapers attach via CDP.

set "DEBUG_PROFILE=%~dp0..\config\chrome_debug_profile"

REM Free port 9222 if a previous side-Chrome is still bound to it.
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":9222 " 2^>nul') do (
  taskkill /F /PID %%a 2>nul
)
timeout /t 1 /nobreak >nul

start "" "C:\Program Files\Google\Chrome\Application\chrome.exe" ^
  --remote-debugging-port=9222 ^
  --user-data-dir="%DEBUG_PROFILE%" ^
  --no-default-browser-check ^
  --no-first-run ^
  --disable-blink-features=AutomationControlled ^
  https://seller-uk.tiktok.com/homepage

echo Side-profile Chrome launched on debug port 9222.
echo Profile dir: %DEBUG_PROFILE%
echo Verify: http://localhost:9222/json/version
