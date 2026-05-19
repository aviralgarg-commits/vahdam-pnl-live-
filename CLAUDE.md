# Vahdam P&L Live — operational notes

These are the conventions and gotchas you need to keep the dashboard accurate. Skim before editing any data pipeline code.

## Architecture (no Windsor)

```
TikTok Seller Center (UK + US)
  ├─ Orders        ── scrape_orders.py        ─┐
  ├─ Affiliate     ── scrape_affiliate.py     ─┤
  ├─ Marketing/Ads ── scrape_ads.py           ─┤
  └─ Smart Promo   ── scrape_smart_promo.py   ─┤
                                              ├──> aggregate_affiliate.py
                                              │    (re-aggregates affiliate
                                              │     CSVs into pnl_daily.json
                                              │     aff_daily section)
                                              │
                                              └──> build_dashboard.py
                                                   │
                                                   ▼
                                              public/index.html ──> Vercel auto-deploy

verify_against_sheets.py reads ~/Downloads/Vahdam _ Inventory Planning Tiktok.xlsx
and ~/Downloads/Overall Analysis USA.xlsx (NOT the "(1)" duplicates) via
openpyxl(data_only=True) AFTER every refresh. Output: logs/cm_check_*.md.
```

All four scrapers attach to the user's real Chrome via Playwright `connect_over_cdp` on `http://localhost:9222`. The user runs `scripts/launch_chrome_debug.bat` once per boot (or pins it to `shell:startup`). Auth, cookies, and service workers are all maintained by Chrome itself — no `launch_persistent_context`, no `storage_state.json`.

## Critical business rules (NON-NEGOTIABLE)

### UK VAT (20% removed from Net Sales for zero-rated supplements)

- `Coffee` — from **2026-04-01** onwards
- `Green Burner`, `Ashwagandha Caps`, `Turmeric Curcumin` — always
- `Turmeric Ginger Tea` — KEEPS VAT (non-supplement)
- Formula: `vat_in_sales = net_sales × (20/120)`; `net_sales_ex_vat = net_sales − vat_in_sales`

### UK per-order shipping
£1.99/order added to COGs from **2026-03-01** onwards.

### UK VAT recovery on TikTok fees
- Seller Center shows VAT-EXCL for Ad Spend and Smart Promo
- Gross up ×1.20 → VAT-inclusive cash outflow
- VAT recovery = `(ad_spend_inc + smart_promo_inc) × (20/120)`

### Affiliate commission
- Total = `Standard + Shop Ads + Co-funded creator bonus`; for each, use **Actual** if > 0 else **Estimated**
- Exclude rows where `Order Status = Ineligible`; keep `Settled` + `Pending`
- Date parsing: **DD/MM/YYYY** from `Time Created`
- CSV layout: UK 31 cols (with "Creator Region"), US 30 cols — `aggregate_affiliate.py` auto-detects via header

### Order status filter (net_orders)
Include `COMPLETED + DELIVERED + SHIPPED + AWAITING_COLLECTION + IN_TRANSIT`. Exclude `CANCELLED + AWAITING_SHIPMENT`. (See `config/order_filters.json`.)

### Order CSV date formats
UK uses **DD/MM/YYYY**, US uses **MM/DD/YYYY**. Currency-prefixed strings ("GBP 22.32") need regex-strip before float parse.

### SKU nickname priority (when deriving from product name)
1. `frother` → Frother (free gift)
2. `mushroom coffee` → Coffee
3. `ashwagandha coffee` → Coffee
4. `ksm-66 coffee` (or `ksm-66` + `coffee`) → Coffee
5. `instant coffee` → Coffee
6. `curcumin` OR `curcuminoids` → Turmeric Curcumin (**only after coffee checks** — Coffee SKUs containing "Curcuminoids" otherwise misclassify)
7. `ashwagandha` + capsule → Ashwagandha Caps
8. `green burner` → Green Burner
9. `shatavari` → Shatavari (US only)
10. `turmeric ginger tea` → Turmeric Ginger Tea
11. `moringa` → Moringa (excluded from UK)
12. `butterfly pea` → Butterfly Pea (free gift)

### Region rules
- UK sells: Coffee, Turmeric Curcumin, Ashwagandha Caps, Green Burner, Turmeric Ginger Tea
- US sells: Coffee, Turmeric Curcumin, Ashwagandha Caps, Shatavari (**no Pack of 5, no Ginger Tea**)
- US has NO VAT, NO per-order shipping surcharge (shipping is included in Fulfillment)

### TT commission
9% UK, 6% US.

### Free sample cost
- UK: per-pack rates from `data/uk_costs.json` → `uk_free_sample_costs`; **subtract £2 shipping** for samples from **2026-02-14** onwards.
- US: sum of `COGS + DSF + Storage + LogDuty + LogCost + Fulfillment + Shipping` (excludes Commission + VAT).

### Display currency
- Region = UK → GBP
- Region = US → USD
- Region = Both → USD (UK × FX rate, default 1.27)

## CDP scraper architecture (DO NOT regress)

Why `connect_over_cdp` and NOT `launch_persistent_context`:

- `launch_persistent_context` with `storage_state.json` LOSES TikTok service-worker auth (we tried; it loops on login forever).
- A cloned profile path (`chrome_profiles/uk/`) fails to decrypt cookies — Chrome 127+ App-Bound Encryption ties cookie keys to the source `user_data_dir` path.
- Pointing Playwright at the REAL `User Data\Profile N` in place fails Chrome 136+'s "non-default data directory" check for `--remote-debugging-port` (and `--remote-debugging-pipe`).
- Claude-in-Chrome MCP cannot help — TikTok domains are on its extension denylist.

What works: launch a single Chrome with `--remote-debugging-port=9222` against the user's normal `User Data\Default` (no sync issue since `Default` is the local-only Chrome profile). Playwright attaches via CDP to that running browser. Auth survives forever as long as the user doesn't sign out of TikTok Seller Center.

See `scripts/_cdp.py` for the shared `attach()` / `detach()` / `shared_scrape_setup()` helpers.

## Defensive patterns (Seller Center is flaky)

Verified failure mode 2026-05-19: `/ads-creation/dashboard`, `/order/list`, `/affiliate/orders` all returned sidebar-only pages on UK. Each scraper handles this:

- **Pre-flight**: navigate to `{region}/homepage`, confirm DOM contains `VAHDAM` within 10s. If not → `AUTH_LOST_{region}` + skip.
- **Per scrape**: 2 retries with 15s backoff.
- **DOM<500 chars after retries** → `PAGE_NOT_LOADED_{region}_{page}` + skip + screenshot to `logs/debug_*_dim.png`.
- **Shadow DOM**: the Marketing dashboard renders inside a shadow tree; `innerText` misses it. Scrapers use the `SHADOW_TEXT_JS` walker from `_cdp.py` via `page.evaluate()`.
- **Smart Promo URL**: use `/promotion/program-center/smart-program/register`, NOT `/manage`. The register page is more reliable and exposes metrics as `"ROI X.X GMV £X Seller promotion cost £X Orders X New customers X"` in a single text block.

## Smart Promo bucket is APPEND-ONLY

Each scrape adds a new bucket to `data/smart_promo_monthly.json` with non-overlapping `window_start..window_end`. **Never overwrite existing buckets** — the dashboard's allocator handles multiple windows correctly (allocates by daily revenue share within each bucket window). `scrape_smart_promo.py` starts the new window at `latest_existing_window_end + 1 day`.

## Verifier (`verify_against_sheets.py`)

Reads via `openpyxl(data_only=True)`:

- **UK**: `~/Downloads/Vahdam _ Inventory Planning Tiktok.xlsx` (NOT the `(1)` duplicate). Tab auto-detected by searching for `CM1` + `CM2` headers.
- **US**: `~/Downloads/Overall Analysis USA.xlsx`. If no CM1/CM2 columns, logs `US sheet missing CM tab` and skips US verification.

For each common date: Δ% < 1% → ✓, 1–5% → ⚠, ≥ 5% → ✗.

**Never silently force dashboard to match sheet.** If sheet is wrong, write report. If dashboard is wrong, patch + push. If ambiguous, write specific question (with date + values + driving line item + 2–3 plausible causes) to `logs/cm_check_questions.md`.

Output: `logs/cm_check_{YYYY-MM-DD-HHmm}.md` + one-line summary in `logs/refresh.log`.

## Daily refresh order (refresh_daily.py)

```
0. ensure_chrome_running       (launches launch_chrome_debug.bat if :9222 dead)
1. scrape_orders.py            UK + US
2. scrape_ads.py               UK + US
3. scrape_affiliate.py         UK + US
4. scrape_smart_promo.py       UK + US
5. aggregate_affiliate.py      Rebuild aff_daily from raw_csvs/
6. build_dashboard.py
7. git add data/ public/ raw_csvs/ seller_center_snapshots/ ; commit ; push
8. verify_against_sheets.py
```

Task Scheduler (Windows): `VahdamPnL_MorningUK` @ 15:30 IST (= 11:00 Europe/London), `VahdamPnL_EveningUS` @ 03:30 IST (= 15:00 America/Los_Angeles previous day). Both `WakeToRun=true`.

## Common bugs & their fixes

| Symptom | Likely cause | Fix |
|---|---|---|
| All UK SKU rows in zero state | Chrome not on :9222 OR TikTok session expired | Run `launch_chrome_debug.bat`; verify by hitting <http://localhost:9222/json/version> |
| Affiliate commission < expected | Forgot to exclude "Ineligible" status, OR using MM/DD instead of DD/MM | Inspect raw CSV header; `aggregate_affiliate.py` should auto-detect |
| Smart Promo doubled | Buckets overlap | Buckets must be append-only with non-overlapping windows — check `data/smart_promo_monthly.json` |
| Coffee with "Curcuminoids" routed to Turmeric Curcumin | SKU priority order broken | Coffee checks MUST run before curcumin in `nick_from_name` |
| Net Sales matches but CM2 doesn't | UK VAT not subtracted for new SKU, OR shipping surcharge missing | Check `data/uk_costs.json` rules table |
| `CDP_UNAVAILABLE` in scrape logs | Chrome not running | Re-run `scripts/launch_chrome_debug.bat` |
| `AUTH_LOST_{region}` | TikTok session expired | Open Chrome (already on 9222), log into seller-uk + seller-us tabs |
| `PAGE_NOT_LOADED_{region}_{page}` | TikTok sidebar-only render (flaky) | Already retried 2× with 15s backoff; last-known values are kept |
| Verifier reports "missing CM tab" | xlsx uses row-oriented CM layout | Acceptable per spec — verifier skips that region gracefully |

## Deprecated (Windsor era)

Files renamed to `*.deprecated` (kept locally, gitignored):

- `scripts/fetch_windsor.py.deprecated`
- `scripts/merge_pnl.py.deprecated`
- `scripts/ingest_seller.py.deprecated`
- `data/windsor_*.json.deprecated`
- `data/windsor_cache.deprecated/`

Do not bring these back. Windsor.ai is no longer a dependency.
