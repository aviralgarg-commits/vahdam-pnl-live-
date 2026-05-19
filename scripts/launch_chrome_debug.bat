@echo off
REM Launch the user's real Chrome with --remote-debugging-port=9222 so
REM Playwright scrapers can attach via CDP. Uses the Default profile in
REM the standard User Data dir — all logins (TikTok Seller Center via
REM Google SSO) persist because we never created a sandbox context.
REM
REM Add a shortcut to this .bat to shell:startup so Chrome+debug-port
REM are always running after login.

taskkill /F /IM chrome.exe 2>nul
timeout /t 2 /nobreak >nul
start "" "C:\Program Files\Google\Chrome\Application\chrome.exe" ^
  --remote-debugging-port=9222 ^
  --user-data-dir="C:\Users\Aviral Garg\AppData\Local\Google\Chrome\User Data" ^
  --profile-directory="Default" ^
  https://seller-uk.tiktok.com/homepage
