"""
scrape_affiliate.py — drive Chrome via Playwright to download fresh affiliate
order CSVs from TikTok Seller Center (UK + US). Idempotent: only fetches the
date gap between the most recent CSV in raw_csvs/ and today.

Setup (one-time, per region):
  1) pip install playwright && playwright install chromium
  2) Run once interactively to log in and persist auth:
       python scripts/scrape_affiliate.py --setup-uk
       python scripts/scrape_affiliate.py --setup-us
     A Chromium window opens. Log in to TikTok Seller Center. Close when done.
     Auth state is saved to config/playwright_storage_{uk,us}.json.
  3) Subsequent runs (including from refresh_daily.py) use headless mode + the
     stored auth — no manual interaction needed.

If Playwright is not installed or auth state is missing, the script logs a
warning and exits 0 (the pipeline continues; CSVs land manually instead).
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

UK_URL = "https://seller-uk.tiktok.com/affiliate/orders"
US_URL = "https://seller-us.tiktok.com/affiliate/orders"


def log(msg: str) -> None:
    line = f"[{_dt.now().strftime('%Y-%m-%d %H:%M:%S')}] {msg}"
    print(line)
    with LOG.open("a", encoding="utf-8") as fh:
        fh.write(line + "\n")


def latest_csv_dates() -> tuple[str | None, str | None]:
    """Return (latest UK order date, latest US order date) from existing CSVs.
    Reads each CSV's 'Time Created' column (DD/MM/YYYY) to find the actual data
    cutoff, not just the file mtime."""
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
                has_uk_col = "Creator Region" in header
                off = 0 if has_uk_col else -1
                idx_time = 26 + off
                idx_ccy = 6
                for row in reader:
                    if len(row) <= idx_time:
                        continue
                    raw = row[idx_time]
                    m = _re.match(r"(\d{1,2})/(\d{1,2})/(\d{4})", raw or "")
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


def storage_state_path(region: str) -> pathlib.Path:
    return CONFIG_DIR / f"playwright_storage_{region.lower()}.json"


def setup_auth(region: str) -> int:
    """Interactive: open a non-headless window so the user can log in."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        log("ERROR: playwright not installed. Run: pip install playwright && playwright install chromium")
        return 1
    url = UK_URL if region.upper() == "UK" else US_URL
    sp = storage_state_path(region)
    log(f"Setup {region}: opening Chromium. Log in to Seller Center, then close the window.")
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        ctx = browser.new_context()
        page = ctx.new_page()
        page.goto(url, wait_until="domcontentloaded", timeout=120_000)
        # Wait for the user to close the browser
        try:
            while not page.is_closed():
                time.sleep(2)
        except Exception:
            pass
        ctx.storage_state(path=str(sp))
        browser.close()
    log(f"Saved auth state -> {sp}")
    return 0


def download_csvs(region: str, gap_from: str, gap_to: str) -> int:
    """Headless Playwright run to export affiliate CSVs covering gap_from..gap_to."""
    try:
        from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout
    except ImportError:
        log("ERROR: playwright not installed.")
        return 1
    sp = storage_state_path(region)
    if not sp.exists():
        log(f"ERROR: no auth state for {region} at {sp}. Run --setup-{region.lower()} first.")
        return 1
    url = UK_URL if region.upper() == "UK" else US_URL
    log(f"{region}: downloading CSVs for {gap_from} -> {gap_to}")
    downloaded: list[pathlib.Path] = []
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            ctx = browser.new_context(storage_state=str(sp), accept_downloads=True)
            page = ctx.new_page()
            page.goto(url, wait_until="domcontentloaded", timeout=60_000)
            # NOTE: TikTok's Seller Center DOM is volatile. The selectors below are
            # placeholders pinned to common element patterns. They may need updating
            # when TikTok ships UI changes. Wrap in try/except so partial breakage
            # doesn't kill the pipeline.
            try:
                page.wait_for_selector('input[placeholder*="Start" i], input[placeholder*="start" i]', timeout=15_000)
            except PWTimeout:
                log(f"{region}: date picker did not appear within 15s — Seller Center may be slow or auth expired")
                browser.close()
                return 2
            # Click date input → custom range
            inputs = page.query_selector_all('input[placeholder*="date" i], input[placeholder*="Date" i]')
            if len(inputs) >= 2:
                inputs[0].fill(gap_from)
                inputs[1].fill(gap_to)
                page.keyboard.press("Enter")
            else:
                log(f"{region}: could not locate two date inputs; selectors need updating")
            # Wait for table to load
            page.wait_for_timeout(3000)
            # Trigger export — common button text: "Export", "Download"
            export_btn = page.query_selector('button:has-text("Export"), button:has-text("Download")')
            if not export_btn:
                log(f"{region}: Export button not found")
                browser.close()
                return 3
            with page.expect_download(timeout=120_000) as dl_info:
                export_btn.click()
            dl = dl_info.value
            target = DOWNLOADS / dl.suggested_filename
            dl.save_as(str(target))
            downloaded.append(target)
            browser.close()
    except Exception as e:
        log(f"{region}: scrape failed — {e}")
        return 4

    # Move new affiliate_orders_*.csv files into raw_csvs/
    moved = 0
    existing = {p.name for p in RAW_CSVS.glob("affiliate_orders_*.csv")}
    for src in downloaded:
        if not src.name.startswith("affiliate_orders_") or not src.name.endswith(".csv"):
            continue
        if src.name in existing:
            continue
        shutil.move(str(src), str(RAW_CSVS / src.name))
        moved += 1
        log(f"{region}: moved {src.name} -> raw_csvs/")
    log(f"{region}: {moved} new CSV(s) added to raw_csvs/")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--setup-uk", action="store_true")
    parser.add_argument("--setup-us", action="store_true")
    args = parser.parse_args()

    if args.setup_uk:
        return setup_auth("UK")
    if args.setup_us:
        return setup_auth("US")

    today = _date.today().isoformat()
    uk_latest, us_latest = latest_csv_dates()
    log(f"Latest order dates in raw_csvs/: UK={uk_latest}, US={us_latest}")

    # Pick gap_from = max(latest + 1 day, today - 7) so we always re-check the last week
    week_ago = (_date.today() - timedelta(days=7)).isoformat()
    uk_from = max(uk_latest, week_ago) if uk_latest else week_ago
    us_from = max(us_latest, week_ago) if us_latest else week_ago

    rc = 0
    rc += download_csvs("UK", uk_from, today)
    rc += download_csvs("US", us_from, today)
    return rc


if __name__ == "__main__":
    sys.exit(main())
