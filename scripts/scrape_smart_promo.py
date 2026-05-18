"""
scrape_smart_promo.py — drive Chrome via Playwright to capture Smart Promotion
metrics from TikTok Seller Center (UK + US). Appends a new bucket per region to
data/smart_promo_monthly.json covering the gap since the last captured bucket.

Setup is shared with scrape_affiliate.py (same persistent auth state):
  python scripts/scrape_affiliate.py --setup-uk   # one-time, opens browser
  python scripts/scrape_affiliate.py --setup-us   # one-time
"""
from __future__ import annotations

import json
import pathlib
import re
import sys
import time
from datetime import datetime as _dt, date as _date, timedelta

ROOT = pathlib.Path(__file__).resolve().parent.parent
CONFIG_DIR = ROOT / "config"
SMART_PROMO_FILE = ROOT / "data" / "smart_promo_monthly.json"
LOG = ROOT / "logs" / "scrape_smart_promo.log"
LOG.parent.mkdir(exist_ok=True)

UK_URL = "https://seller-uk.tiktok.com/promotion/program-center/smart-program/manage"
US_URL = "https://seller-us.tiktok.com/promotion/program-center/smart-program/manage"


def log(msg: str) -> None:
    line = f"[{_dt.now().strftime('%Y-%m-%d %H:%M:%S')}] {msg}"
    print(line)
    with LOG.open("a", encoding="utf-8") as fh:
        fh.write(line + "\n")


def storage_state_path(region: str) -> pathlib.Path:
    return CONFIG_DIR / f"playwright_storage_{region.lower()}.json"


def latest_bucket_end(region: str) -> str | None:
    """Latest window_end across existing Smart Promo buckets for this region."""
    if not SMART_PROMO_FILE.exists():
        return None
    data = json.loads(SMART_PROMO_FILE.read_text(encoding="utf-8-sig"))
    ends = [b.get("window_end") for b in data if b.get("region") == region and b.get("window_end")]
    return max(ends) if ends else None


def parse_money(s: str) -> float:
    if s is None:
        return 0.0
    s = str(s).strip().replace(",", "").replace("£", "").replace("$", "").replace(" ", "")
    if s.endswith("%"):
        try:
            return float(s[:-1]) / 100.0
        except ValueError:
            return 0.0
    try:
        return float(s)
    except ValueError:
        return 0.0


def parse_int(s: str) -> int:
    try:
        return int(round(parse_money(s)))
    except Exception:
        return 0


def capture(region: str) -> dict | None:
    """Returns a smart-promo bucket dict, or None on failure."""
    try:
        from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout
    except ImportError:
        log("ERROR: playwright not installed.")
        return None

    sp = storage_state_path(region)
    if not sp.exists():
        log(f"ERROR: no auth state for {region}. Run scripts/scrape_affiliate.py --setup-{region.lower()} first.")
        return None

    url = UK_URL if region.upper() == "UK" else US_URL

    last_end = latest_bucket_end(region)
    today = _date.today()
    if last_end:
        gap_from = (_date.fromisoformat(last_end) + timedelta(days=1)).isoformat()
    else:
        gap_from = today.replace(day=1).isoformat()
    gap_to = today.isoformat()

    if gap_from > gap_to:
        log(f"{region}: no gap to capture (last bucket already covers through today)")
        return None

    log(f"{region}: capturing Smart Promo for {gap_from} -> {gap_to}")

    for attempt in range(2):
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                ctx = browser.new_context(storage_state=str(sp))
                page = ctx.new_page()
                page.goto(url, wait_until="domcontentloaded", timeout=60_000)
                page.wait_for_timeout(3000)

                # Click "View details" on the Smart Promotion Plan row
                view_btn = page.query_selector(
                    'button:has-text("View details"), a:has-text("View details")'
                )
                if not view_btn:
                    log(f"{region}: 'View details' button not found on Manage page (attempt {attempt+1})")
                    browser.close()
                    time.sleep(15)
                    continue
                view_btn.click()
                page.wait_for_load_state("domcontentloaded", timeout=30_000)
                page.wait_for_timeout(3000)

                # Set custom date range — placeholder selectors; may need adjustment
                date_inputs = page.query_selector_all('input[placeholder*="date" i]')
                if len(date_inputs) >= 2:
                    date_inputs[0].fill(gap_from)
                    date_inputs[1].fill(gap_to)
                    page.keyboard.press("Enter")
                    page.wait_for_timeout(3000)
                else:
                    log(f"{region}: date pickers not found — falling back to default (MTD)")

                # Read metrics from the DOM. Selectors are placeholders — adjust by
                # inspecting the live page once.
                body = page.inner_text("body")

                def grab(label_re: str) -> str | None:
                    m = re.search(label_re + r"[^\n0-9$£%-]*([\-£$\d.,%]+)", body, re.IGNORECASE)
                    return m.group(1) if m else None

                cost_str = grab(r"Seller (?:promotion )?cost") or grab(r"Cost\b")
                gmv_str = grab(r"\bGMV\b") or grab(r"Smart Promotion GMV")
                roi_str = grab(r"\bROI\b")
                orders_str = grab(r"Orders\b") or grab(r"Orders via")
                new_cust_str = grab(r"New customers?")
                fee_rate_str = grab(r"Seller fee") if region.upper() == "US" else None

                if not cost_str or not gmv_str:
                    log(f"{region}: failed to extract cost/GMV from page (attempt {attempt+1})")
                    if attempt == 0:
                        browser.close()
                        time.sleep(15)
                        continue
                    browser.close()
                    return None

                bucket = {
                    "region": region.upper(),
                    "month": gap_from[:7],
                    "window_start": gap_from,
                    "window_end": gap_to,
                    "cost": parse_money(cost_str),
                    "currency": "GBP" if region.upper() == "UK" else "USD",
                    "smart_promo_gmv": parse_money(gmv_str) if gmv_str else 0.0,
                    "orders_via_smart_promo": parse_int(orders_str) if orders_str else 0,
                    "new_customers": parse_int(new_cust_str) if new_cust_str else 0,
                    "roi": parse_money(roi_str) if roi_str else 0.0,
                    "source": f"TikTok {region.upper()} Seller Center > Marketing > Smart Promotion",
                    "pulled_at": today.isoformat(),
                }
                if fee_rate_str:
                    bucket["seller_fee_rate"] = parse_money(fee_rate_str)
                browser.close()
                return bucket
        except Exception as e:
            log(f"{region}: scrape error (attempt {attempt+1}) — {e}")
            time.sleep(15)
    return None


def append_bucket(bucket: dict) -> None:
    data: list[dict] = []
    if SMART_PROMO_FILE.exists():
        data = json.loads(SMART_PROMO_FILE.read_text(encoding="utf-8-sig"))
    # Dedup by (region, window_start, window_end)
    key = (bucket["region"], bucket["window_start"], bucket["window_end"])
    data = [b for b in data if (b.get("region"), b.get("window_start"), b.get("window_end")) != key]
    data.append(bucket)
    SMART_PROMO_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")


def main() -> int:
    captured = 0
    for region in ("UK", "US"):
        b = capture(region)
        if b is None:
            log(f"{region}: Smart Promo bucket not refreshed — will retry next refresh")
            continue
        append_bucket(b)
        log(f"{region}: appended bucket {b['window_start']} -> {b['window_end']} cost={b['currency']} {b['cost']}")
        captured += 1
    log(f"Smart Promo capture complete: {captured}/2 regions refreshed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
