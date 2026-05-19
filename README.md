# Vahdam P&L Live

Static HTML dashboard built from TikTok Seller Center exports (Orders, Affiliate, Ad Spend, Smart Promotion) into a daily-refreshed P&L view with CM1 / CM2 for UK + US. Deployed to Vercel.

**Data architecture**: TikTok Seller Center scraping (Playwright via CDP, attached to the user's real Chrome) + manual CSV exports + manually-maintained costs. **No Windsor**, no third-party data APIs.

## Quick start

```powershell
cd C:\Users\Aviral Garg\vahdam-pnl-live

# One-off venv setup
uv venv --python 3.11
venv\Scripts\python.exe -m pip install -r requirements.txt   # or: fastapi uvicorn[standard] requests python-dotenv openpyxl playwright

# Build the dashboard from current data
venv\Scripts\python.exe scripts\build_dashboard.py

# Serve locally
python -m http.server 8000 --directory public
# Dashboard: http://localhost:8000/
```

Live URL: <https://vahdam-pnl-live.vercel.app/>

## Daily refresh pipeline (`scripts/refresh_daily.py`)

```
0. ensure_chrome_running      Chrome must be up on :9222 (or launches the .bat)
1. scrape_orders.py           UK + US "All Order" CSVs → raw_csvs/
2. scrape_ads.py              UK + US GMV Max dashboard → data/ad_spend_30d.json
3. scrape_affiliate.py        UK + US paginated affiliate CSVs → raw_csvs/
4. scrape_smart_promo.py      UK + US Smart Promotion → APPEND-ONLY smart_promo_monthly.json
5. aggregate_affiliate.py     Re-aggregate affiliate CSVs → pnl_daily.json
6. build_dashboard.py         → public/index.html
7. git commit + push          → Vercel rebuilds
8. verify_against_sheets.py   Diff CM1/CM2 vs user's local xlsx → logs/cm_check_*.md
```

## Chrome via CDP — one-time setup

Scrapers attach to the user's real Chrome via Chrome DevTools Protocol on port 9222. This bypasses Playwright's launch_persistent_context (which loses TikTok service-worker auth) and Claude-in-Chrome's TikTok domain denylist.

```powershell
# One-time, or add to shell:startup
C:\Users\Aviral Garg\vahdam-pnl-live\scripts\launch_chrome_debug.bat
```

The .bat launches Chrome with `--remote-debugging-port=9222 --user-data-dir=<user profile>`. As long as you're logged into TikTok Seller Center in that Chrome (UK + US tabs), scrapers run headless-attach with zero auth steps.

## Windows Task Scheduler

| Task | Time (IST local) | Equivalent |
|---|---|---|
| `VahdamPnL_MorningUK` | 15:30 | 11:00 Europe/London |
| `VahdamPnL_EveningUS` | 03:30 next day | 15:00 America/Los_Angeles |

Both invoke `refresh_daily.bat`, run `WakeToRun=true`, `StartWhenAvailable=true`. Created by:

```powershell
schtasks /Create /TN "VahdamPnL_MorningUK" /TR "C:\Users\Aviral Garg\vahdam-pnl-live\refresh_daily.bat" /SC DAILY /ST 15:30 /F
schtasks /Create /TN "VahdamPnL_EveningUS" /TR "C:\Users\Aviral Garg\vahdam-pnl-live\refresh_daily.bat" /SC DAILY /ST 03:30 /F
# Then via Schedule.Service COM: WakeToRun=true on both (see commit history for the one-liner).
```

## Environment variables (`.env`)

| Variable | Description |
|---|---|
| `HOST` / `PORT` | FastAPI server bind (default `0.0.0.0:8000`) |
| `CHROME_DEBUG_PORT` | CDP port the scrapers attach to (default `9222`) |

## Manual data files

| File | When to update | How |
|---|---|---|
| `data/uk_costs.json` | Pack costs change | Edit JSON directly |
| `data/us_costs.json` | Pack costs change | Edit JSON directly |
| `data/pnl_daily.json` `monthly_history` | Monthly | Drop from UK/US reporting workbooks |
| `data/pnl_daily.json` `creatives` | Weekly (optional) | Snapshot from Seller Center |
| `raw_csvs/affiliate_orders_*.csv` | Auto via scraper, manual fallback | Drop new files; run aggregate_affiliate.py |
| `raw_csvs/All order*.csv` | Auto via scraper, manual fallback | Drop new files |

## Pipeline scripts

| Script | Purpose |
|---|---|
| `scripts/launch_chrome_debug.bat` | Start Chrome with CDP port 9222 |
| `scripts/_cdp.py` | Shared `attach()` / `detach()` helpers |
| `scripts/scrape_orders.py` | Download All-order CSVs (UK + US) |
| `scripts/scrape_ads.py` | Ad-spend dashboard snapshots (UK + US) |
| `scripts/scrape_affiliate.py` | Affiliate-orders CSVs paginated (UK + US) |
| `scripts/scrape_smart_promo.py` | Smart Promotion bucket (UK + US, append-only) |
| `scripts/aggregate_affiliate.py` | Rebuild aff_daily section of pnl_daily.json |
| `scripts/build_dashboard.py` | Build `public/index.html` |
| `scripts/verify_against_sheets.py` | Reconcile CM1/CM2 vs user's local xlsx |
| `scripts/refresh_daily.py` | Orchestrator (all of the above in sequence) |

Files ending in `.deprecated` are the retired Windsor-era pipeline — kept locally for reference, not committed.

## Troubleshooting

- **`CDP_UNAVAILABLE` in logs**: `launch_chrome_debug.bat` not running. Start it.
- **`AUTH_LOST_<region>`**: Chrome's TikTok session expired. Open Chrome (already running on 9222), log into seller-uk.tiktok.com and seller-us.tiktok.com, re-run scraper.
- **`PAGE_NOT_LOADED_<region>_<page>`**: Seller Center returned a sidebar-only page (transient). Scraper retries 2× with 15s backoff; if still failing, last-known values are kept and a screenshot lands in `logs/debug_*_dim.png`.
- **Dashboard shows old numbers**: Run `scripts/refresh_daily.py` manually to bypass the scheduler.
- **Port 8000 in use**: Set `PORT=8001` in `.env`.
