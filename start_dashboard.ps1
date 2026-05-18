# start_dashboard.ps1 — Launch FastAPI server + Cloudflare Quick Tunnel.
# Writes the public URL to public_url.txt so the user can find it after a reboot.
#
# Usage: just double-click, or let Task Scheduler run it at logon.

$ErrorActionPreference = "Continue"
$root = "C:\Users\Aviral Garg\vahdam-pnl-live"
Set-Location $root

$logsDir = Join-Path $root "logs"
if (-not (Test-Path $logsDir)) { New-Item -ItemType Directory -Path $logsDir | Out-Null }

$serverLog = Join-Path $logsDir "server.log"
$urlFile   = Join-Path $root  "public_url.txt"

# Kill any existing server / tunnel so we don't double-bind
Get-Process cloudflared -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
$port8000 = netstat -ano | findstr ":8000" | findstr "LISTENING"
if ($port8000) {
    $pidNum = ($port8000 -split '\s+')[-1]
    Stop-Process -Id $pidNum -Force -ErrorAction SilentlyContinue
}
Start-Sleep -Seconds 2

# 1) Start FastAPI server
$pythonExe = Join-Path $root "venv\Scripts\python.exe"
Start-Process -FilePath $pythonExe `
    -ArgumentList "server.py" `
    -WorkingDirectory $root `
    -WindowStyle Hidden `
    -RedirectStandardOutput $serverLog `
    -RedirectStandardError "$serverLog.err"

# Wait for server to bind to 8000
for ($i = 0; $i -lt 30; $i++) {
    Start-Sleep -Seconds 1
    if (netstat -ano | findstr ":8000" | findstr "LISTENING") { break }
}

# 2) Start Cloudflare Quick Tunnel on a fixed metrics port so we can scrape the URL.
$cfExe = Join-Path $root "cloudflared.exe"
$metricsPort = 20241
Start-Process -FilePath $cfExe `
    -ArgumentList "tunnel","--url","http://localhost:8000","--no-autoupdate","--metrics","127.0.0.1:$metricsPort" `
    -WindowStyle Hidden

# 3) Pull the tunnel URL from cloudflared's Prometheus metrics endpoint.
$publicUrl = $null
for ($i = 0; $i -lt 60; $i++) {
    Start-Sleep -Seconds 1
    try {
        $m = Invoke-WebRequest "http://127.0.0.1:$metricsPort/metrics" -TimeoutSec 2 -UseBasicParsing -ErrorAction Stop
        $match = [regex]::Match($m.Content, 'userHostname="(https://[a-z0-9-]+\.trycloudflare\.com)"')
        if ($match.Success) {
            $publicUrl = $match.Groups[1].Value
            break
        }
    } catch {}
}

if ($publicUrl) {
    "$publicUrl" | Set-Content -Path $urlFile -NoNewline
    Write-Host "Dashboard public URL: $publicUrl"
    Write-Host "Saved to: $urlFile"
} else {
    Write-Host "Tunnel started but URL not captured within 60s. Check http://127.0.0.1:$metricsPort/metrics"
}
