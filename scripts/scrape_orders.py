"""
scrape_orders.py — Download "All order" CSV exports from Seller Center for
UK + US covering last_pull..today. Drops files into raw_csvs/.

Architecture: connect_over_cdp to user's real Chrome (port 9222). See
scripts/_cdp.py for why.

Defensive (Seller Center sidebar-only failure mode observed 2026-05-19):
  - Pre-flight: /homepage must show VAHDAM marker within 10s, else skip region
  - Per region: 2 retries with 15s backoff
  - If page DOM < 500 chars after retries -> log PAGE_NOT_LOADED + skip
"""
from __future__ import annotations

import pathlib
import re
import shutil
import sys
import time
from datetime import datetime as _dt, date as _date, timedelta

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

LOG = ROOT / "logs" / "scrape_orders.log"
LOG.parent.mkdir(exist_ok=True)
RAW = ROOT / "raw_csvs"
DOWNLOADS = pathlib.Path.home() / "Downloads"

ORDERS_URL = {
    "UK": "https://seller-uk.tiktok.com/order/list/index",
    "US": "https://seller-us.tiktok.com/order/list/index",
}


def log(msg: str) -> None:
    line = f"[{_dt.now().strftime('%Y-%m-%d %H:%M:%S')}] {msg}"
    print(line)
    with LOG.open("a", encoding="utf-8") as fh:
        fh.write(line + "\n")


def latest_csv_date_for(region: str) -> str | None:
    """Latest 'Created Time' across All-order CSVs in raw_csvs/, scoped by region.
    UK uses DD/MM/YYYY, US uses MM/DD/YYYY."""
    import csv as _csv
    latest = None
    for fp in sorted(RAW.glob("All order*.csv")):
        try:
            with fp.open(encoding="utf-8-sig", errors="replace", newline="") as fh:
                reader = _csv.DictReader(fh)
                for row in reader:
                    country = (row.get("Country") or "").strip()
                    if region == "UK" and country.lower() in ("england","scotland","wales","northern ireland","anglia","united kingdom"):
                        pass
                    elif region == "US" and country.lower() in ("united states","usa"):
                        pass
                    else:
                        continue
                    ct = (row.get("Created Time") or "").strip().strip('"')
                    if not ct:
                        continue
                    parts = ct.split(" ")[0].split("/")
                    if len(parts) != 3:
                        continue
                    if region == "UK":
                        # DD/MM/YYYY
                        iso = f"{parts[2]}-{int(parts[1]):02d}-{int(parts[0]):02d}"
                    else:
                        # MM/DD/YYYY
                        iso = f"{parts[2]}-{int(parts[0]):02d}-{int(parts[1]):02d}"
                    if (latest is None) or iso > latest:
                        latest = iso
        except Exception:
            continue
    return latest


def scrape_region(region: str) -> int:
    from _cdp import shared_scrape_setup, detach  # type: ignore

    setup = shared_scrape_setup(region, ORDERS_URL[region], log)
    if setup is None:
        return 2
    pw, browser, ctx, page = setup

    last = latest_csv_date_for(region)
    today = _date.today().isoformat()
    gap_from = last or (_date.today() - timedelta(days=7)).isoformat()
    log(f"{region}: orders gap_from={gap_from} -> {today}")

    try:
        for attempt in range(2):
            try:
                page.goto(ORDERS_URL[region], wait_until="domcontentloaded", timeout=60_000)
                try:
                    page.wait_for_load_state("networkidle", timeout=20_000)
                except Exception:
                    pass
                page.wait_for_timeout(6000)

                body = ""
                try:
                    body = page.inner_text("body", timeout=2000)
                except Exception:
                    pass
                if len(body) < 500:
                    log(f"PAGE_NOT_LOADED_{region}_orders (DOM<500 chars, attempt {attempt+1})")
                    time.sleep(15)
                    continue

                # Click "Export" / "Download" — TikTok's button text varies
                # between locales and versions. Try several selectors.
                export_btn = None
                for sel in (
                    'button:has-text("Export")',
                    'button:has-text("Download")',
                    'button:has-text("Export orders")',
                    '[role="button"]:has-text("Export")',
                ):
                    eb = page.query_selector(sel)
                    if eb and eb.is_visible():
                        export_btn = eb
                        break
                if not export_btn:
                    log(f"{region}: Export button not found (attempt {attempt+1})")
                    page.screenshot(path=str(ROOT / "logs" / f"debug_orders_{region.lower()}_no_export.png"))
                    time.sleep(15)
                    continue

                with page.expect_download(timeout=120_000) as dl_info:
                    export_btn.click()
                dl = dl_info.value
                target = RAW / dl.suggested_filename
                dl.save_as(str(target))
                log(f"{region}: downloaded {dl.suggested_filename} -> raw_csvs/")
                return 0
            except Exception as e:
                log(f"{region}: scrape attempt {attempt+1} failed -- {e}")
                time.sleep(15)
        return 4
    finally:
        try:
            if not page.is_closed():
                page.close()
        except Exception:
            pass
        detach(pw, browser)


def main() -> int:
    log(f"=== scrape_orders.py {_date.today().isoformat()} ===")
    rc_uk = scrape_region("UK")
    rc_us = scrape_region("US")
    log(f"Done: UK rc={rc_uk}, US rc={rc_us}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
