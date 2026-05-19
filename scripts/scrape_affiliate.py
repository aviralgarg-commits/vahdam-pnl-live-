"""
scrape_affiliate.py — Download affiliate-orders CSVs from Seller Center
(UK + US) via CDP attach to user's real Chrome. Paginated: TikTok exports
per page, not as one file.

Pre-flight: /homepage must show VAHDAM marker within 10s (shared_scrape_setup).
"""
from __future__ import annotations

import pathlib
import shutil
import sys
import time
from datetime import datetime as _dt, date as _date, timedelta

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

LOG = ROOT / "logs" / "scrape_affiliate.log"
LOG.parent.mkdir(exist_ok=True)
RAW = ROOT / "raw_csvs"
DOWNLOADS = pathlib.Path.home() / "Downloads"

ORDERS_URL = {
    "UK": "https://seller-uk.tiktok.com/affiliate/orders",
    "US": "https://seller-us.tiktok.com/affiliate/orders",
}


def log(msg: str) -> None:
    line = f"[{_dt.now().strftime('%Y-%m-%d %H:%M:%S')}] {msg}"
    print(line)
    with LOG.open("a", encoding="utf-8") as fh:
        fh.write(line + "\n")


def latest_csv_dates() -> tuple[str | None, str | None]:
    """Latest 'Time Created' (DD/MM/YYYY) per region across raw_csvs/."""
    import csv as _csv
    import re as _re
    uk_max = us_max = None
    for fp in sorted(RAW.glob("affiliate_orders_*.csv")):
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


def scrape_region(region: str, gap_from: str, gap_to: str) -> int:
    from _cdp import shared_scrape_setup, detach  # type: ignore

    setup = shared_scrape_setup(region, ORDERS_URL[region], log)
    if setup is None:
        return 2
    pw, browser, ctx, page = setup

    downloaded: list[pathlib.Path] = []
    try:
        for attempt in range(2):
            try:
                page.goto(ORDERS_URL[region], wait_until="domcontentloaded", timeout=60_000)
                try:
                    page.wait_for_load_state("networkidle", timeout=25_000)
                except Exception:
                    pass
                page.wait_for_timeout(8000)

                body = ""
                try:
                    body = page.inner_text("body", timeout=2000)
                except Exception:
                    pass
                if len(body) < 500:
                    log(f"PAGE_NOT_LOADED_{region}_affiliate_orders (DOM<500, attempt {attempt+1})")
                    time.sleep(15)
                    continue

                # Date picker (set Yesterday preset where applicable)
                try:
                    start_input = page.query_selector('input[placeholder*="Start" i]')
                    if start_input:
                        start_input.click()
                        page.wait_for_timeout(800)
                        yday_iso = (_date.today() - timedelta(days=1)).isoformat()
                        today_iso = _date.today().isoformat()
                        yday_btn = page.query_selector('button:text-is("Yesterday")')
                        if gap_from == yday_iso and gap_to == today_iso and yday_btn:
                            yday_btn.click()
                            log(f"{region}: clicked Yesterday preset")
                        else:
                            date_inputs = page.query_selector_all('input[placeholder*="date" i]')
                            if len(date_inputs) >= 2:
                                date_inputs[0].fill(""); date_inputs[0].type(gap_from)
                                date_inputs[1].fill(""); date_inputs[1].type(gap_to)
                                page.keyboard.press("Enter")
                                log(f"{region}: set custom range {gap_from} -> {gap_to}")
                except Exception as e:
                    log(f"{region}: date picker error -- {e}")
                page.wait_for_timeout(3000)

                # Pagination — TikTok exports per page
                try:
                    pc_el = page.query_selector('[class*="pagination" i] [class*="total" i]')
                    total_pages = 1
                    if pc_el:
                        import re as _re
                        m = _re.search(r"(\d+)", pc_el.inner_text())
                        if m:
                            total_pages = int(m.group(1))
                    log(f"{region}: pagination ~{total_pages} page(s)")
                except Exception:
                    total_pages = 1

                for idx in range(1, total_pages + 1):
                    try:
                        export_btn = page.query_selector(
                            'button:has-text("Download"), button:has-text("Export")'
                        )
                        if not export_btn:
                            log(f"{region}: page {idx} -- Download button not found")
                            break
                        with page.expect_download(timeout=120_000) as dl_info:
                            export_btn.click()
                        dl = dl_info.value
                        target = DOWNLOADS / dl.suggested_filename
                        dl.save_as(str(target))
                        downloaded.append(target)
                        log(f"{region}: page {idx} -> {dl.suggested_filename}")
                    except Exception as e:
                        log(f"{region}: page {idx} export failed -- {e}")
                        break
                    if idx < total_pages:
                        next_btn = page.query_selector(
                            '[class*="pagination" i] button:has-text(">"), button[aria-label*="next" i]'
                        )
                        if next_btn and not next_btn.is_disabled():
                            next_btn.click()
                            page.wait_for_timeout(2500)
                        else:
                            break
                break  # success path — exit retry loop
            except Exception as e:
                log(f"{region}: affiliate scrape attempt {attempt+1} failed -- {e}")
                time.sleep(15)
    finally:
        try:
            if not page.is_closed():
                page.close()
        except Exception:
            pass
        detach(pw, browser)

    # Move downloads into raw_csvs/, skip dups
    existing = {p.name for p in RAW.glob("affiliate_orders_*.csv")}
    moved = 0
    for src in downloaded:
        if not src.name.startswith("affiliate_orders_") or not src.name.endswith(".csv"):
            continue
        if src.name in existing:
            log(f"{region}: skip dup {src.name}")
            continue
        shutil.move(str(src), str(RAW / src.name))
        moved += 1
    log(f"{region}: {moved} new CSV(s) added (of {len(downloaded)} downloaded)")
    return 0


def main() -> int:
    log(f"=== scrape_affiliate.py {_date.today().isoformat()} ===")
    today = _date.today().isoformat()
    week_ago = (_date.today() - timedelta(days=7)).isoformat()
    uk_latest, us_latest = latest_csv_dates()
    log(f"Latest dates in raw_csvs/: UK={uk_latest}, US={us_latest}")
    uk_from = max(uk_latest, week_ago) if uk_latest else week_ago
    us_from = max(us_latest, week_ago) if us_latest else week_ago
    rc_uk = scrape_region("UK", uk_from, today)
    rc_us = scrape_region("US", us_from, today)
    log(f"Done: UK rc={rc_uk}, US rc={rc_us}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
