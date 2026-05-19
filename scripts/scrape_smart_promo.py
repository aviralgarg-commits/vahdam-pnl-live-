"""
scrape_smart_promo.py — Pull Smart Promotion buckets from Seller Center
(UK + US) via CDP attach. Appends to data/smart_promo_monthly.json AND
seller_center_snapshots/<region>/smart_promo_<from>_to_<to>.json.

Per spec:
  - Use /promotion/program-center/smart-program/register (NOT /manage —
    register is more reliable; data appears as a single text block:
    "ROI X.X GMV £X Seller promotion cost £X Orders X New customers X")
  - Window: latest existing window_end + 1d -> today (so we never overlap)
  - APPEND-ONLY: never overwrite existing buckets; the dashboard's
    allocator handles overlapping windows correctly.
  - Shadow-aware text extraction via SHADOW_TEXT_JS.
"""
from __future__ import annotations

import json
import pathlib
import re
import sys
import time
from datetime import datetime as _dt, date as _date, timedelta

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

LOG = ROOT / "logs" / "scrape_smart_promo.log"
LOG.parent.mkdir(exist_ok=True)
SMART_PROMO_FILE = ROOT / "data" / "smart_promo_monthly.json"
SNAPSHOTS = ROOT / "seller_center_snapshots"

REGISTER_URL = {
    "UK": "https://seller-uk.tiktok.com/promotion/program-center/smart-program/register",
    "US": "https://seller-us.tiktok.com/promotion/program-center/smart-program/register",
}


def log(msg: str) -> None:
    line = f"[{_dt.now().strftime('%Y-%m-%d %H:%M:%S')}] {msg}"
    print(line)
    with LOG.open("a", encoding="utf-8") as fh:
        fh.write(line + "\n")


def parse_money(s) -> float:
    if s is None: return 0.0
    s = str(s).strip().replace(",", "").replace("£", "").replace("$", "").replace(" ", "")
    if s.endswith("%"):
        try: return float(s[:-1]) / 100.0
        except ValueError: return 0.0
    try: return float(s)
    except ValueError: return 0.0


def parse_int(s) -> int:
    try: return int(round(parse_money(s)))
    except Exception: return 0


def latest_bucket_end(region: str) -> str | None:
    """Largest window_end for this region in smart_promo_monthly.json. We
    start the next scrape from latest_end + 1 day so windows never overlap."""
    if not SMART_PROMO_FILE.exists():
        # Also check pnl_daily.json's embedded buckets
        pnl = ROOT / "data" / "pnl_daily.json"
        if pnl.exists():
            try:
                data = json.loads(pnl.read_text(encoding="utf-8-sig"))
                ends = [b.get("window_end") for b in data.get("smart_promo_monthly", [])
                        if b.get("region") == region and b.get("window_end")]
                return max(ends) if ends else None
            except Exception:
                return None
        return None
    data = json.loads(SMART_PROMO_FILE.read_text(encoding="utf-8-sig"))
    if isinstance(data, dict):
        data = data.get("buckets", [])
    ends = [b.get("window_end") for b in data
            if b.get("region") == region and b.get("window_end")]
    return max(ends) if ends else None


def capture(region: str) -> dict | None:
    from _cdp import shared_scrape_setup, detach, SHADOW_TEXT_JS  # type: ignore

    last_end = latest_bucket_end(region)
    today = _date.today()
    if last_end:
        gap_from = (_date.fromisoformat(last_end) + timedelta(days=1)).isoformat()
    else:
        gap_from = today.replace(day=1).isoformat()
    gap_to = today.isoformat()
    if gap_from > gap_to:
        log(f"{region}: no gap to capture (latest bucket {last_end} already covers today)")
        return None
    log(f"{region}: capturing Smart Promo for {gap_from} -> {gap_to}")

    setup = shared_scrape_setup(region, REGISTER_URL[region], log)
    if setup is None:
        return None
    pw, browser, ctx, page = setup

    try:
        for attempt in range(2):
            try:
                page.goto(REGISTER_URL[region], wait_until="domcontentloaded", timeout=60_000)
                try:
                    page.wait_for_load_state("networkidle", timeout=25_000)
                except Exception:
                    pass
                page.wait_for_timeout(8000)

                # Shadow-aware text extraction
                txt = page.evaluate(SHADOW_TEXT_JS)
                if not txt or len(txt) < 500:
                    log(f"PAGE_NOT_LOADED_{region}_smart_promo_register (text<500, attempt {attempt+1})")
                    try:
                        page.screenshot(path=str(ROOT / "logs" / f"debug_smart_promo_{region.lower()}_dim.png"))
                    except Exception:
                        pass
                    time.sleep(15)
                    continue

                # Pull the metrics block:
                #   "ROI X.X GMV £X Seller promotion cost £X Orders X New customers X"
                ccy = "GBP" if region.upper() == "UK" else "USD"

                def grab(pat: str) -> str | None:
                    m = re.search(pat + r"\s*[^\d£$\-]{0,30}([\-£$\d.,]+%?)", txt, re.IGNORECASE)
                    return m.group(1) if m else None

                roi = grab(r"\bROI\b")
                gmv = grab(r"\bGMV\b")
                cost = grab(r"Seller\s+promotion\s+cost") or grab(r"\bCost\b")
                orders = grab(r"\bOrders\b")
                new_cust = grab(r"New\s+customers?")
                fee_rate = grab(r"Seller\s+fee") if region.upper() == "US" else None

                if not cost or not gmv:
                    log(f"{region}: failed to extract cost/GMV from register page (attempt {attempt+1})")
                    time.sleep(15)
                    continue

                bucket = {
                    "region": region.upper(),
                    "month": gap_from[:7],
                    "window_start": gap_from,
                    "window_end": gap_to,
                    "cost": round(parse_money(cost), 2),
                    "currency": ccy,
                    "smart_promo_gmv": round(parse_money(gmv), 2),
                    "orders_via_smart_promo": parse_int(orders) if orders else 0,
                    "new_customers": parse_int(new_cust) if new_cust else 0,
                    "roi": parse_money(roi) if roi else 0.0,
                    "source": f"TikTok {region.upper()} Seller Center > Marketing > Smart Promotion",
                    "pulled_at": today.isoformat(),
                }
                if fee_rate:
                    bucket["seller_fee_rate"] = parse_money(fee_rate)

                # Append-only: snapshot to per-region file
                snap_dir = SNAPSHOTS / region.upper()
                snap_dir.mkdir(parents=True, exist_ok=True)
                snap = snap_dir / f"smart_promo_{gap_from}_to_{gap_to}.json"
                snap.write_text(json.dumps({
                    "region": region.upper(),
                    "source": bucket["source"],
                    "pulled_at": bucket["pulled_at"],
                    "window_start": gap_from,
                    "window_end": gap_to,
                    "metrics": {
                        "roi": bucket["roi"],
                        "gmv": bucket["smart_promo_gmv"],
                        "seller_promotion_cost": bucket["cost"],
                        "orders_via_smart_promo": bucket["orders_via_smart_promo"],
                        "new_customers": bucket["new_customers"],
                    },
                    "currency": ccy,
                }, indent=2), encoding="utf-8")
                log(f"{region}: snapshot -> {snap.name}")
                return bucket
            except Exception as e:
                log(f"{region}: smart promo scrape attempt {attempt+1} failed -- {e}")
                time.sleep(15)
        return None
    finally:
        try:
            if not page.is_closed():
                page.close()
        except Exception:
            pass
        detach(pw, browser)


def append_bucket(bucket: dict) -> None:
    """APPEND-ONLY merge into smart_promo_monthly.json. Never overwrite an
    existing (region, window_start, window_end) — log + skip if collision."""
    data: list[dict] = []
    if SMART_PROMO_FILE.exists():
        try:
            data = json.loads(SMART_PROMO_FILE.read_text(encoding="utf-8-sig"))
            if isinstance(data, dict):
                data = data.get("buckets", [])
        except Exception:
            data = []
    key = (bucket["region"], bucket["window_start"], bucket["window_end"])
    for b in data:
        if (b.get("region"), b.get("window_start"), b.get("window_end")) == key:
            log(f"{bucket['region']}: bucket {key} already exists — APPEND-ONLY, skipping")
            return
    data.append(bucket)
    SMART_PROMO_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")
    log(f"{bucket['region']}: appended bucket {bucket['window_start']} -> {bucket['window_end']} "
        f"cost={bucket['currency']} {bucket['cost']:.2f}")


def main() -> int:
    log(f"=== scrape_smart_promo.py {_date.today().isoformat()} ===")
    for region in ("UK", "US"):
        b = capture(region)
        if b is None:
            log(f"{region}: bucket not refreshed this cycle")
            continue
        append_bucket(b)
    return 0


if __name__ == "__main__":
    sys.exit(main())
