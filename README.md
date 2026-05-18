# Vahdam P&L Live

FastAPI dashboard pulling live TikTok Shop orders + ad spend from Windsor.ai, affiliate data from Seller Center CSV exports, and serving `public/index.html` rebuilt daily.

## Quick start

```powershell
# First-time setup (one-off)
cd C:\Users\Aviral Garg\vahdam-pnl-live

# Create and activate venv (Python 3.11 via uv)
uv venv --python 3.11
venv\Scripts\python.exe -m pip install fastapi uvicorn[standard] requests python-dotenv

# First refresh (pulls Windsor data, ingests CSVs, builds dashboard)
venv\Scripts\python.exe scripts\refresh_daily.py

# Start server
venv\Scripts\python.exe server.py
# Dashboard: http://localhost:8000/
# Health:    http://localhost:8000/api/health
# Refresh:   POST http://localhost:8000/api/refresh
```

## Environment variables (`.env`)

| Variable | Description |
|---|---|
| `WINDSOR_API_KEY` | Windsor.ai API key |
| `WINDSOR_BASE_URL` | `https://connectors.windsor.ai/all` |
| `TT_SHOP_DATA_SOURCE_UK` | TikTok Shop UK account ID |
| `TT_SHOP_DATA_SOURCE_US` | TikTok Shop US account ID |
| `TT_ADS_DATA_SOURCE_UK` | TikTok Ads UK account ID |
| `TT_ADS_DATA_SOURCE_US` | TikTok Ads US account ID |
| `WINDSOR_LOOKBACK_DAYS` | Days of history to pull (default 90) |
| `HOST` / `PORT` | Server bind (default `0.0.0.0:8000`) |

## Manual data files (update periodically)

| File | How to update |
|---|---|
| `raw_csvs/affiliate_orders_*.csv` | Export from TikTok Seller Center → Affiliate → Orders |
| `data/smart_promo_monthly.json` | Update monthly from Seller Center → Marketing → Smart Promotion |
| `data/monthly_history.json` | Update monthly from UK/US reporting workbooks |
| `data/uk_costs.json` | Update when pack costs change |
| `data/us_costs.json` | Update when pack costs change |
| `data/creatives.json` | Update when creative snapshots change (optional) |

### Affiliate CSV naming

Files must be named `affiliate_orders_*.csv`. UK CSVs have 31 columns (includes "Creator Region"); US have 30.

## Windows Task Scheduler (daily 7 AM)

Run once in an elevated PowerShell to register the task:

```powershell
$action = New-ScheduledTaskAction -Execute "C:\Users\Aviral Garg\vahdam-pnl-live\refresh_daily.bat"
$trigger = New-ScheduledTaskTrigger -Daily -At "07:00"
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable
Register-ScheduledTask -TaskName "Vahdam PnL Daily Refresh" -Action $action -Trigger $trigger -Settings $settings -RunLevel Highest
```

Logs are written to `logs\refresh.log`.

## Cloudflare Tunnel (public URL)

```powershell
# One-off install (no admin needed)
winget install cloudflare.cloudflared

# Start tunnel (generates a public HTTPS URL)
cloudflared tunnel --url http://localhost:8000
```

The URL is printed to stdout. Re-run after each restart or use a named tunnel for a stable URL.

## Pipeline scripts

| Script | Purpose |
|---|---|
| `scripts/fetch_windsor.py` | Pull orders + ad spend from Windsor.ai |
| `scripts/ingest_seller.py` | Parse affiliate CSVs + load smart_promo |
| `scripts/merge_pnl.py` | Merge all sources → `data/pnl_daily.json` |
| `scripts/build_dashboard.py` | Build `public/index.html` from pnl_daily.json |
| `scripts/refresh_daily.py` | Orchestrator: runs all four steps in sequence |

## Data sources

- **Orders**: Windsor.ai `tiktok_shop` connector, accounts `GBLC43Q29H` (UK) and `USLCEGEVCN` (US)
- **Ad spend**: Windsor.ai `tiktok` connector, accounts `7506508260422287376` (UK) and `7393105007056388112` (US)
- **Affiliate commissions**: Manual CSV export from TikTok Seller Center
- **Smart Promotion**: Manual entry in `data/smart_promo_monthly.json`
- **Monthly history**: Manual entry in `data/monthly_history.json`

## Troubleshooting

**Windsor returns empty data**: Check `.env` API key and account IDs. Windsor sometimes delays new data by ~24h.

**Affiliate CSV not parsed**: File must be named `affiliate_orders_*.csv`. Check date format is DD/MM/YYYY.

**Dashboard shows no data**: Run `scripts/refresh_daily.py` manually and check output for errors.

**Port 8000 in use**: Set `PORT=8001` in `.env` before starting the server.
