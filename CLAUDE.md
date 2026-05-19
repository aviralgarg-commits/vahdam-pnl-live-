# Vahdam P&L Live — operational notes

These are the conventions and gotchas you (or future-me) need to know to keep
the dashboard accurate. Skim before editing any data pipeline code.

## Architecture

```
Windsor.ai API           ┐
  - tiktok          (ads)│
  - tiktok_shop  (orders)│ ──> fetch_windsor.py    ┐
  - tiktok_shop  (stmt)  ┘                          │
                                                    ├──> merge_pnl.py ──> pnl_daily.json
Seller Center exports                               │                       │
  - raw_csvs/affiliate_orders_*.csv ──> ingest_seller.py                     │
  - raw_csvs/All order-UK-*.csv (fallback) ──> aggregate_orders.py           │
                                                    │                       ▼
Seller Center Chrome scrape                         │                build_dashboard.py
  - scrape_affiliate.py (Playwright)                │                       │
  - scrape_smart_promo.py (Playwright) ─> data/smart_promo_monthly.json    │
                                                                            ▼
                                               public/index.html ──> Vercel auto-deploy

verify_against_sheets.py reads C:\Users\...\Downloads\*.xlsx via openpyxl, runs after every refresh.
```

## Order status filter (NET_ORDER_STATUSES)

`config/order_filters.json` defines which tiktok_shop statuses count toward `net_orders / net_qty / net_sales`.

Default = **Option A** (matches the user's working sheets):
```json
"net_order_statuses": ["COMPLETED", "DELIVERED", "AWAITING_COLLECTION", "IN_TRANSIT", "SHIPPED"]
```

Rationale:
- Sheet counts "actually fulfilled" orders — anything that has shipped or is at/with the customer.
- `AWAITING_SHIPMENT` and other pre-ship states are tracked as `inflight_orders` and **excluded** from net.
- `CANCELLED` is tracked separately in the cancelled bucket.
- `REFUNDED` keeps counting as net; the refund value is subtracted via the refund line item.

To change the filter, edit `config/order_filters.json` and re-run `scripts/refresh_daily.py`. No code change needed.

**Expected residual drift vs the sheet:** snapshots taken at different points in time will diverge because the *same* order can flip from `AWAITING_SHIPMENT` to `SHIPPED` between captures. Older dates in the sheet (when many orders were still in flight at capture) will show fewer net orders than the dashboard does today. This is correct behaviour, not a bug.

## Date timezone bucketing

`fetch_windsor.aggregate_shop_orders` groups orders by **shop-local** timezone:
- UK shop (`GBLC43Q29H`) → `Europe/London` (GMT/BST)
- US shop (`USLCEGEVCN`) → `America/Los_Angeles` (PST/PDT)

This matches how TikTok Seller Center's Order Report groups orders for daily totals. Using UTC drifts ~1-2 hours of orders into the wrong day near midnight.

Windsor's `date_from`/`date_to` filter is UTC. We pull `date_to + 1 day` to catch US orders placed late evening PDT that Windsor stamps to the next UTC calendar day.

## Windsor UK outage handling

The UK `tiktok_shop` account (`GBLC43Q29H`) periodically drops from Windsor's connector list (OAuth token expiry, manual disconnect, etc.). `fetch_windsor.run()` detects this and logs `WINDSOR_UK_DISCONNECTED` to `logs/windsor_health.log` when:
- 0 UK rows are returned for a window, AND
- US returned > 0 rows in the same window

When this happens:
1. Do NOT treat the 0 as actual data ("UK net sales = £0").
2. Fall back to manual `All order-UK-*.csv` exports from Seller Center, dropped into `raw_csvs/`.
3. `aggregate_orders.py` (TBD — see TODO list) ingests these and produces UK orders_daily entries with the same schema as the Windsor path.
4. Reconnect tiktok_shop UK at https://windsor.ai/connectors when you're able.
5. Once reconnected, the next refresh picks UK back up automatically and CSV fallback becomes redundant.

Verify reconnect with:
```powershell
.\venv\Scripts\python.exe -c "from scripts.fetch_windsor import fetch_shop_orders; rows = fetch_shop_orders('2026-05-12', '2026-05-19'); print('UK rows:', sum(1 for r in rows if r.get('account_id') == 'GBLC43Q29H'))"
```

## Affiliate CSV scraper (Playwright)

`scripts/scrape_affiliate.py` drives Chromium via Playwright to download fresh affiliate CSVs from `seller-{uk,us}.tiktok.com/affiliate/orders`. State stored in `config/playwright_storage_{uk,us}.json`.

Setup (one-time per region, requires interactive login):
```
.\venv\Scripts\python.exe .\scripts\scrape_affiliate.py --setup-uk
.\venv\Scripts\python.exe .\scripts\scrape_affiliate.py --setup-us
```

**Known UK setup gotcha**: logging in via Google SSO doesn't persist usable cookies — Playwright redirects back to login on the next run. Use direct email/password login during setup.

**Known US gotcha**: `/affiliate/orders` page renders blank when navigated via deep URL in Playwright. Either click through from the sidebar menu or it's a permissions issue on the account. Re-investigate selectors after auth state is renewed.

## Smart Promotion scraper (Playwright)

`scripts/scrape_smart_promo.py` captures Smart Promo metrics from
`seller-{uk,us}.tiktok.com/promotion/program-center/smart-program/manage`.

Anchors:
- Row label: `"Smart Promotion"` (US) or `"Smart Promotion Plan"` (UK)
- `View details` button inside that `<tr>`
- Date picker: focus start-date input → click `<button>Yesterday</button>` preset
- Metrics on detail page: ROI, GMV, Seller promotion cost, Orders, New customers — all extracted from `Smart Promotion metrics` section by label-to-value regex (allows newlines between label and value)

Appends a new bucket to `data/smart_promo_monthly.json` — **never overwrites** existing buckets. Multiple adjacent buckets (e.g. May 1-13 + May 14-19) are valid; the dashboard's revenue-share allocator handles them correctly.

## Verifier (openpyxl)

`scripts/verify_against_sheets.py` reads the user's working spreadsheets directly via `openpyxl` with `data_only=True` (cached formula values). Sources:
- UK: `C:\Users\Aviral Garg\Downloads\Vahdam _ Inventory Planning Tiktok.xlsx`
- US: `C:\Users\Aviral Garg\Downloads\Overall Analysis USA.xlsx`

**Never use the `(1)` duplicate files** — those are stale browser-downloaded copies.

If a sheet's last populated date is > 1 day older than `pnl_daily.json`'s `window_end`, dates beyond the sheet's coverage are skipped (with a log line) — staleness doesn't block the run, and UK staleness doesn't affect US (and vice versa).

If a cached formula cell is empty (formula not yet evaluated by Excel), it's skipped with a log line. The user needs to open + save the workbook for the cache to populate.

## Verifier output is the source of truth for "where are the gaps"

`logs/cm_check_<timestamp>.md` after every refresh contains the per-day reconciliation table. `logs/cm_check_questions.md` collects any drift ≥ 5%.

**Never patch the dashboard to match the sheet**. The sheet is the verification source, not the data source. If the verifier flags a drift, debug the data pipeline (Windsor / scrape / merge) — not the dashboard's numbers.

## Schedules

Two Windows scheduled tasks fire `refresh_daily.bat`:
- `VahdamDashboard_MorningRefresh_UK` — 15:30 IST daily (= 11:00 Europe/London)
- `VahdamDashboard_EveningRefresh_US` — 03:30 IST daily (= 15:00 America/Los_Angeles next-day-pacific)

Each task runs:
1. `fetch_google_sheets.py` (no-op without service-account JSON)
2. `fetch_windsor.py` — ads + tiktok_shop orders + statement aff fees
3. `scrape_affiliate.py` — Playwright Seller Center CSV download
4. `scrape_smart_promo.py` — Playwright Smart Promo bucket capture
5. `ingest_seller.py` — re-aggregate raw_csvs/ from scratch
6. `merge_pnl.py` — combine into pnl_daily.json (overlay + Windsor top-up + statement aff top-up)
7. `build_dashboard.py` — rebuild public/index.html
8. `verify_against_sheets.py` — reconcile vs xlsx, write report + questions

After successful refresh, `refresh_daily.bat` auto-commits + pushes to GitHub `main`, which triggers Vercel auto-deploy.

## Live URLs

- Vercel: https://vahdam-pnl-live.vercel.app/
- Cloudflare quick tunnel (rotates per reboot): see `public_url.txt`

## Quick troubleshooting

| Symptom | Likely cause |
|---|---|
| UK numbers all zero | Windsor UK disconnected. Check `logs/windsor_health.log` for `WINDSOR_UK_DISCONNECTED`. |
| Dashboard data stale by 1 day for a region | Schedule didn't run (laptop sleeping?). Check `logs/refresh.log` for last successful entry. |
| Day-by-day drift > 5% on net_orders | Status filter or capture-time mismatch. Read "Order status filter" above. |
| Affiliate scrape says AUTH REQUIRED | Cookies expired. Re-run `--setup-uk` or `--setup-us`. |
| Verifier crashes with `charmap codec` | Windows console can't print unicode. Logs use ASCII-only summary — should be fixed. |
| Vercel deploy didn't trigger | `refresh_daily.bat` git step failed. Check end of `logs/refresh.log` for git errors. |
