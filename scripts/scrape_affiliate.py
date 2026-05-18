"""
scrape_affiliate.py — Playwright-driven affiliate-order CSV downloader.

Pre-flight auth check: navigates to {region}/homepage and confirms 'VAHDAM'
(or the seller name) appears in DOM within 10 seconds. If not, logs
"AUTH REQUIRED" and SKIPS that region (never attempts to log in on the user's
behalf). UK auth failure does not block US, and vice versa.

Pagination: TikTok Seller Center exports CSV per page, not as one big file.
The scraper iterates through pages and downloads each.

One-time setup:
  pip install playwright && playwright install chromium
  python scripts/scrape_affiliate.py --setup-uk    # opens browser, log in once
  python scripts/scrape_affiliate.py --setup-us
"""
from __future__ import annotations

import argparse
import json
import pathlib
import shutil
import sys
import time
from datetime import datetime as _dt, date as _date, timedelta

ROOT = pathlib.Path(__file__).resolve().parent.parent
CONFIG_DIR = ROOT / "config"
CONFIG_DIR.mkdir(exist_ok=True)
RAW_CSVS = ROOT / "raw_csvs"
DOWNLOADS = pathlib.Path.home() / "Downloads"
LOG = ROOT / "logs" / "scrape_affiliate.log"
LOG.parent.mkdir(exist_ok=True)

HOMEPAGE = {
    "UK": "https://seller-uk.tiktok.com/homepage",
    "US": "https://seller-us.tiktok.com/homepage",
}
ORDERS_URL = {
    "UK": "https://seller-uk.tiktok.com/affiliate/orders",
    "US": "https://seller-us.tiktok.com/affiliate/orders",
}
AUTH_TIMEOUT_SEC = 10
AUTH_MARKERS = ["VAHDAM", "Vahdam"]


def log(msg: str) -> None:
    line = f"[{_dt.now().strftime('%Y-%m-%d %H:%M:%S')}] {msg}"
    print(line)
    with LOG.open("a", encoding="utf-8") as fh:
        fh.write(line + "\n")


def storage_state_path(region: str) -> pathlib.Path:
    return CONFIG_DIR / f"playwright_storage_{region.lower()}.json"


def latest_csv_dates() -> tuple[str | None, str | None]:
    """Latest 'Time Created' (DD/MM/YYYY) per region across raw_csvs/."""
    import csv as _csv
    import re as _re
    uk_max = us_max = None
    for fp in sorted(RAW_CSVS.glob("affiliate_orders_*.csv")):
        try:
            with fp.open(encoding="utf-8-sig", errors="replace", newline="") as fh:
                reader = _csv.reader(fh)
                header = next(reader, None)
                if not header or len(header) < 28:
                    continue
                off = 0 if "Creator Region" in header else -1
                idx_time = 26 + off
                idx_ccy = 6
                for row in reader:
                    if len(row) <= idx_time:
                        continue
                    m = _re.match(r"(\d{1,2})/(\d{1,2})/(\d{4})", row[idx_time] or "")
                    if not m:
                        continue
                    iso = f"{m.group(3)}-{int(m.group(2)):02d}-{int(m.group(1)):02d}"
                    ccy = row[idx_ccy] if idx_ccy < len(row) else ""
                    if ccy == "GBP":
                        uk_max = max(uk_max, iso) if uk_max else iso
                    elif ccy == "USD":
                        us_max = max(us_max, iso) if us_max else iso
        except Exception:
            continue
    return uk_max, us_max


def setup_auth(region: str) -> int:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        log("ERROR: playwright not installed. Run: pip install playwright && playwright install chromium")
        return 1
    log(f"Setup {region}: opening Chromium. Log in to TikTok Seller Center, then close window.")
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        ctx = browser.new_context()
        page = ctx.new_page()
        page.goto(HOMEPAGE[region], wait_until="domcontentloaded", timeout=120_000)
        try:
            while not page.is_closed():
                time.sleep(2)
        except Exception:
            pass
        ctx.storage_state(path=str(storage_state_path(region)))
        browser.close()
    log(f"Saved auth state -> {storage_state_path(region)}")
    return 0


def preflight_auth(page, region: str) -> bool:
    """Navigate to homepage, look for AUTH_MARKERS within 10s."""
    try:
        page.goto(HOMEPAGE[region], wait_until="domcontentloaded", timeout=30_000)
    except Exception as e:
        log(f"{region}: homepage navigation failed — {e}")
        return False
    deadline = time.time() + AUTH_TIMEOUT_SEC
    while time.time() < deadline:
        try:
            body = page.inner_text("body")
            if any(m in body for m in AUTH_MARKERS):
                return True
        except Exception:
            pass
        time.sleep(1)
    return False


def scrape_region(region: str, gap_from: str, gap_to: str) -> int:
    try:
        from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout
    except ImportError:
        log("ERROR: playwright not installed.")
        return 1
    sp = storage_state_path(region)
    if not sp.exists():
        log(f"AUTH REQUIRED — {region} no Playwright storage state at {sp}. "
            f"Run: python scripts/scrape_affiliate.py --setup-{region.lower()}")
        return 1

    log(f"{region}: starting scrape for {gap_from} -> {gap_to}")
    downloaded: list[pathlib.Path] = []
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            ctx = browser.new_context(storage_state=str(sp), accept_downloads=True)
            page = ctx.new_page()

            # Pre-flight auth check
            if not preflight_auth(page, region):
                log(f"AUTH REQUIRED — {region} Chrome not logged in (no VAHDAM marker in DOM within "
                    f"{AUTH_TIMEOUT_SEC}s). Skipping. Re-run --setup-{region.lower()}.")
                browser.close()
                return 2
            log(f"{region}: auth ✓")

            # Navigate to affiliate orders
            page.goto(ORDERS_URL[region], wait_until="domcontentloaded", timeout=60_000)
            page.wait_for_timeout(3000)

            # Set custom date range: focus start-date input, click "Yesterday" preset
            # if the gap is exactly yesterday→today; otherwise type in both inputs.
            try:
                start_input = page.query_selector('input[placeholder*="Start" i]')
                if start_input:
                    start_input.click()
                    page.wait_for_timeout(800)
                    yday_btn = page.query_selector('button:text-is("Yesterday")')
                    today_iso = _date.today().isoformat()
                    yday_iso = (_date.today() - timedelta(days=1)).isoformat()
                    if gap_from == yday_iso and gap_to == today_iso and yday_btn:
                        yday_btn.click()
                        log(f"{region}: clicked Yesterday preset")
                    else:
                        # Type both bounds
                        date_inputs = page.query_selector_all('input[placeholder*="date" i]')
                        if len(date_inputs) >= 2:
                            date_inputs[0].fill("")
                            date_inputs[0].type(gap_from)
                            date_inputs[1].fill("")
                            date_inputs[1].type(gap_to)
                            page.keyboard.press("Enter")
                            log(f"{region}: set custom range {gap_from} → {gap_to}")
            except Exception as e:
                log(f"{region}: date picker error — {e}")
            page.wait_for_timeout(3000)

            # PAGINATED export: TikTok exports per page, not in one file.
            # Find pagination control to know how many pages exist.
            try:
                page_count_el = page.query_selector('[class*="pagination" i] [class*="total" i]')
                total_pages = 1
                if page_count_el:
                    txt = page_count_el.inner_text()
                    import re as _re
                    m = _re.search(r"(\d+)\s*(?:page|of|/)", txt, _re.IGNORECASE)
                    if m:
                        total_pages = int(m.group(1))
                log(f"{region}: pagination shows ~{total_pages} page(s)")
            except Exception:
                total_pages = 1

            # Iterate pages — click Download/Export on each, advance
            for page_idx in range(1, total_pages + 1):
                try:
                    export_btn = page.query_selector(
                        'button:has-text("Download"), button:has-text("Export")'
                    )
                    if not export_btn:
                        log(f"{region}: page {page_idx} — Download button not found")
                        break
                    with page.expect_download(timeout=120_000) as dl_info:
                        export_btn.click()
                    dl = dl_info.value
                    target = DOWNLOADS / dl.suggested_filename
                    dl.save_as(str(target))
                    downloaded.append(target)
                    log(f"{region}: page {page_idx} -> {dl.suggested_filename}")
                except Exception as e:
                    log(f"{region}: page {page_idx} export failed — {e}")
                    break

                # Click "next page" if more pages remain
                if page_idx < total_pages:
                    next_btn = page.query_selector(
                        '[class*="pagination" i] button:has-text(">"), '
                        'button[aria-label*="next" i]'
                    )
                    if next_btn and not next_btn.is_disabled():
                        next_btn.click()
                        page.wait_for_timeout(2500)
                    else:
                        log(f"{region}: next-page button missing/disabled — stopping pagination")
                        break

            browser.close()
    except Exception as e:
        log(f"{region}: scrape exception — {e}")
        return 4

    # Move downloads into raw_csvs/, skip dups
    existing = {p.name for p in RAW_CSVS.glob("affiliate_orders_*.csv")}
    moved = 0
    for src in downloaded:
        if not src.name.startswith("affiliate_orders_") or not src.name.endswith(".csv"):
            continue
        if src.name in existing:
            log(f"{region}: skip dup {src.name}")
            continue
        shutil.move(str(src), str(RAW_CSVS / src.name))
        moved += 1
    log(f"{region}: {moved} new CSV(s) added (of {len(downloaded)} downloaded)")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--setup-uk", action="store_true")
    parser.add_argument("--setup-us", action="store_true")
    args = parser.parse_args()
    if args.setup_uk: return setup_auth("UK")
    if args.setup_us: return setup_auth("US")

    today = _date.today().isoformat()
    week_ago = (_date.today() - timedelta(days=7)).isoformat()
    uk_latest, us_latest = latest_csv_dates()
    log(f"Latest order dates in raw_csvs/: UK={uk_latest}, US={us_latest}")
    uk_from = max(uk_latest, week_ago) if uk_latest else week_ago
    us_from = max(us_latest, week_ago) if us_latest else week_ago

    # Run regions independently — failure in one doesn't abort the other
    uk_rc = scrape_region("UK", uk_from, today)
    us_rc = scrape_region("US", us_from, today)
    log(f"Affiliate scrape complete: UK rc={uk_rc}, US rc={us_rc}")
    return 0  # always 0 — failures are reports, not pipeline errors


if __name__ == "__main__":
    sys.exit(main())
