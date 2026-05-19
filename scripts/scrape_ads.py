"""
scrape_ads.py — Pull Shop Ads spend snapshots (GMV Max + LIVE GMV Max + Auto)
from Seller Center for UK + US. Writes per-campaign breakdown to
data/ad_spend_30d.json (overwrites; bucketed by region + campaign).

The Marketing dashboard renders inside a shadow DOM in many TikTok Seller
Center builds — innerText misses it. We use a recursive shadow-walker
(SHADOW_TEXT_JS from _cdp.py) via page.evaluate().

Defensive:
  - 2 retries with 15s backoff per region
  - If shadow-extracted text < 500 chars -> PAGE_NOT_LOADED + skip
"""
from __future__ import annotations

import json
import pathlib
import re
import sys
import time
from datetime import datetime as _dt, date as _date

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

LOG = ROOT / "logs" / "scrape_ads.log"
LOG.parent.mkdir(exist_ok=True)

DASHBOARD_URL = {
    "UK": "https://seller-uk.tiktok.com/ads-creation/dashboard",
    "US": "https://seller-us.tiktok.com/ads-creation/dashboard",
}

AD_SPEND_30D_FILE = ROOT / "data" / "ad_spend_30d.json"


def log(msg: str) -> None:
    line = f"[{_dt.now().strftime('%Y-%m-%d %H:%M:%S')}] {msg}"
    print(line)
    with LOG.open("a", encoding="utf-8") as fh:
        fh.write(line + "\n")


def scrape_region(region: str) -> dict | None:
    from _cdp import shared_scrape_setup, detach, SHADOW_TEXT_JS  # type: ignore
    from playwright.sync_api import TimeoutError as PWTimeout  # type: ignore

    setup = shared_scrape_setup(region, DASHBOARD_URL[region], log)
    if setup is None:
        return None
    pw, browser, ctx, page = setup

    try:
        for attempt in range(2):
            try:
                page.goto(DASHBOARD_URL[region], wait_until="domcontentloaded", timeout=60_000)
                try:
                    page.wait_for_load_state("networkidle", timeout=25_000)
                except Exception:
                    pass
                page.wait_for_timeout(8000)

                # Shadow-aware text extraction
                txt = page.evaluate(SHADOW_TEXT_JS)
                if not txt or len(txt) < 500:
                    log(f"PAGE_NOT_LOADED_{region}_ads_dashboard (text<500 chars, attempt {attempt+1})")
                    try:
                        page.screenshot(path=str(ROOT / "logs" / f"debug_ads_{region.lower()}_dim.png"))
                    except Exception:
                        pass
                    time.sleep(15)
                    continue

                # Total cost: look for "Cost" or "Total cost" labels near a money value.
                ccy = "GBP" if region.upper() == "UK" else "USD"
                ccy_sym = "£" if ccy == "GBP" else "$"
                # crude pull — refine selectors after first live run from screenshot
                m = re.search(rf"Total\s*cost[^\d]{{0,30}}({re.escape(ccy_sym)}?[\d,]+\.?\d*)", txt, re.IGNORECASE)
                total_cost = None
                if m:
                    total_cost = float(m.group(1).replace(ccy_sym, "").replace(",", ""))

                return {
                    "region": region,
                    "currency": ccy,
                    "total_cost": total_cost,
                    "raw_text_len": len(txt),
                    "pulled_at": _date.today().isoformat(),
                    "url": page.url,
                    "notes": "Selector refinement pending — current extraction is best-effort. "
                             "Inspect logs/debug_ads_*.png after first run.",
                }
            except Exception as e:
                log(f"{region}: ads scrape attempt {attempt+1} failed -- {e}")
                time.sleep(15)
        return None
    finally:
        try:
            if not page.is_closed():
                page.close()
        except Exception:
            pass
        detach(pw, browser)


def main() -> int:
    log(f"=== scrape_ads.py {_date.today().isoformat()} ===")
    out = {"pulled_at": _date.today().isoformat()}
    if AD_SPEND_30D_FILE.exists():
        try:
            out = json.loads(AD_SPEND_30D_FILE.read_text(encoding="utf-8-sig"))
        except Exception:
            out = {"pulled_at": _date.today().isoformat()}

    for region in ("UK", "US"):
        snapshot = scrape_region(region)
        if snapshot is not None:
            out[region] = snapshot
            log(f"{region}: total_cost={snapshot.get('total_cost')} ({snapshot.get('currency')})")
        else:
            log(f"{region}: ad spend scrape skipped/failed (keeping previous bucket)")
    out["pulled_at"] = _date.today().isoformat()
    AD_SPEND_30D_FILE.write_text(json.dumps(out, indent=2), encoding="utf-8")
    log(f"Wrote {AD_SPEND_30D_FILE}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
