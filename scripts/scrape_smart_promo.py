"""
scrape_smart_promo.py -- Playwright-driven Smart Promotion bucket capture.

Anchors (validated in prior session):
  - Smart Promo "View details": <tr> containing text "Smart Promotion Plan",
    then find <button> inside that row (NOT <a>)
  - Date picker "Yesterday": <button> with exact text "Yesterday", visible
    only after focusing the start-date input

Pre-flight auth check: confirm 'VAHDAM' appears on /homepage within 10s.
If not, log AUTH REQUIRED and SKIP that region. UK failure doesn't block US.

Appends a new bucket to data/smart_promo_monthly.json -- never overwrites
existing buckets. The dashboard's revenue-share allocator handles adjacent
buckets correctly.

Setup is shared with scrape_affiliate.py -- same Playwright auth state.
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

HOMEPAGE = {
    "UK": "https://seller-uk.tiktok.com/homepage",
    "US": "https://seller-us.tiktok.com/homepage",
}
MANAGE_URL = {
    "UK": "https://seller-uk.tiktok.com/promotion/program-center/smart-program/manage",
    "US": "https://seller-us.tiktok.com/promotion/program-center/smart-program/manage",
}
AUTH_TIMEOUT_SEC = 30
AUTH_MARKERS = ["VAHDAM", "Vahdam", "vahdam"]


def log(msg: str) -> None:
    line = f"[{_dt.now().strftime('%Y-%m-%d %H:%M:%S')}] {msg}"
    print(line)
    with LOG.open("a", encoding="utf-8") as fh:
        fh.write(line + "\n")


def storage_state_path(region: str) -> pathlib.Path:
    return CONFIG_DIR / f"playwright_storage_{region.lower()}.json"


def profile_dir(region: str) -> pathlib.Path:
    """Same persistent Chromium profile dir as scrape_affiliate.py uses."""
    return CONFIG_DIR / f"chrome_profile_{region.lower()}"


def latest_bucket_end(region: str) -> str | None:
    if not SMART_PROMO_FILE.exists():
        return None
    data = json.loads(SMART_PROMO_FILE.read_text(encoding="utf-8-sig"))
    ends = [b.get("window_end") for b in data if b.get("region") == region and b.get("window_end")]
    return max(ends) if ends else None


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


def preflight_auth(page, region: str) -> bool:
    try:
        page.goto(HOMEPAGE[region], wait_until="domcontentloaded", timeout=30_000)
    except Exception as e:
        log(f"{region}: homepage navigation failed -- {e}")
        return False
    deadline = time.time() + AUTH_TIMEOUT_SEC
    while time.time() < deadline:
        try:
            url = page.url or ""
            body = page.inner_text("body", timeout=2000)
            if any(m in body for m in AUTH_MARKERS):
                return True
            on_seller = ("seller-" in url) and ("login" not in url.lower())
            has_login_ui = ("Sign in" in body or "Log in" in body or "Password" in body)
            if on_seller and not has_login_ui and len(body) > 500:
                log(f"{region}: on seller domain, no login UI -- authenticated")
                return True
        except Exception:
            pass
        time.sleep(2)
    return False


def capture(region: str) -> dict | None:
    try:
        from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout
    except ImportError:
        log("ERROR: playwright not installed.")
        return None
    sp = storage_state_path(region)
    pd_ = profile_dir(region)
    has_persistent = pd_.exists() and any(pd_.iterdir())
    if not has_persistent and not sp.exists():
        log(f"AUTH REQUIRED -- {region} no Playwright profile or storage state. "
            f"Run: python scripts/scrape_affiliate.py --setup-{region.lower()}")
        return None

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
                pd = profile_dir(region)
                if pd.exists() and any(pd.iterdir()):
                    # Persistent profile path (SSO survives)
                    ctx = p.chromium.launch_persistent_context(
                        user_data_dir=str(pd),
                        headless=True,
                        args=["--disable-blink-features=AutomationControlled",
                              "--no-default-browser-check", "--no-first-run"],
                    )
                    browser = None
                else:
                    # Legacy fallback
                    browser = p.chromium.launch(headless=True,
                        args=["--disable-blink-features=AutomationControlled"])
                    ctx = browser.new_context(storage_state=str(sp))
                page = ctx.new_page()

                if not preflight_auth(page, region):
                    log(f"AUTH REQUIRED -- {region} Chrome not logged in. Skipping.")
                    _ = (browser.close() if browser else ctx.close())
                    return None
                log(f"{region}: auth OK")

                page.goto(MANAGE_URL[region], wait_until="domcontentloaded", timeout=60_000)
                try:
                    page.wait_for_load_state("networkidle", timeout=30_000)
                except Exception:
                    pass
                page.wait_for_timeout(8000)  # SPA data render hold
                try:
                    page.screenshot(path=str(ROOT / "logs" / f"debug_smart_promo_{region.lower()}_after_load.png"))
                except Exception:
                    pass

                # Dismiss any "Got it" / promotional popups blocking the row
                for txt in ("Got it", "Don't show again", "Close"):
                    try:
                        btn = page.get_by_role("button", name=txt, exact=False)
                        if btn.count() > 0:
                            btn.first.click(timeout=1500)
                            log(f"{region}: dismissed '{txt}' popup")
                            page.wait_for_timeout(800)
                    except Exception:
                        pass

                # Smart Promo row label differs by region:
                #   US: "Smart Promotion"        UK: "Smart Promotion Plan"
                # Anchor on the "View details" button inside any row whose first
                # cell contains either label.
                view_btn = page.locator(
                    'xpath=//tr[.//text()[contains(., "Smart Promotion")]]//button[contains(., "View")]'
                ).first
                try:
                    view_btn.wait_for(state="visible", timeout=10000)
                except PWTimeout:
                    # Fallback: any "View details" button on the page
                    view_btn = page.get_by_role("button", name="View details").first
                    try:
                        view_btn.wait_for(state="visible", timeout=5000)
                    except PWTimeout:
                        log(f"{region}: no 'View details' button found (attempt {attempt+1})")
                    # Dump page HTML for selector debugging
                    try:
                        html = page.content()
                        dbg = ROOT / "logs" / f"debug_smart_promo_{region.lower()}_{int(time.time())}.html"
                        dbg.write_text(html, encoding="utf-8")
                        log(f"{region}: dumped HTML to {dbg.name}")
                    except Exception:
                        pass
                    _ = (browser.close() if browser else ctx.close())
                    time.sleep(15)
                    continue
                view_btn.click()
                page.wait_for_load_state("domcontentloaded", timeout=30_000)
                try:
                    page.wait_for_load_state("networkidle", timeout=20_000)
                except Exception:
                    pass
                page.wait_for_timeout(8000)
                # Detail-page screenshot for selector debugging
                try:
                    page.screenshot(path=str(ROOT / "logs" / f"debug_smart_promo_{region.lower()}_detail.png"), full_page=True)
                    log(f"{region}: dumped detail-page screenshot")
                except Exception:
                    pass

                # Date picker: focus start-date input, click "Yesterday" preset
                start_input = page.query_selector(
                    'input[placeholder*="Start" i], input[placeholder*="start date" i]'
                )
                if start_input:
                    start_input.click()
                    page.wait_for_timeout(800)
                    yday_btn = page.locator('button:text-is("Yesterday")').first
                    try:
                        yday_btn.wait_for(state="visible", timeout=4000)
                        yday_btn.click()
                        log(f"{region}: clicked Yesterday preset")
                        page.wait_for_timeout(2500)
                    except PWTimeout:
                        # Fallback: type custom range
                        date_inputs = page.query_selector_all('input[placeholder*="date" i]')
                        if len(date_inputs) >= 2:
                            date_inputs[0].fill("")
                            date_inputs[0].type(gap_from)
                            date_inputs[1].fill("")
                            date_inputs[1].type(gap_to)
                            page.keyboard.press("Enter")
                            log(f"{region}: typed custom range {gap_from} -> {gap_to}")
                            page.wait_for_timeout(2500)

                # Read metrics from page body text. Labels and values are on
                # separate lines (ROI\n8.02), so the gap regex must allow \n.
                body = page.inner_text("body")

                def grab(label_re: str) -> str | None:
                    # Allow up to 30 non-digit chars (incl whitespace/newlines) between label and value
                    m = re.search(label_re + r"\s*[^\d$£%\-]{0,30}([\-£$\d.,]+%?)",
                                  body, re.IGNORECASE)
                    return m.group(1) if m else None

                # Anchor metric extraction on the "Smart Promotion metrics" section
                # (avoids picking up the 3.5% rate near "Manage your marketing plan").
                metrics_idx = body.find("Smart Promotion metrics")
                metrics_body = body[metrics_idx:] if metrics_idx >= 0 else body

                def grab_in_metrics(label_re: str) -> str | None:
                    m = re.search(label_re + r"\s*[^\d$£%\-]{0,30}([\-£$\d.,]+%?)",
                                  metrics_body, re.IGNORECASE)
                    return m.group(1) if m else None

                cost_str = grab_in_metrics(r"Seller promotion cost") or grab_in_metrics(r"\bCost\b")
                gmv_str = grab_in_metrics(r"\bGMV\b")
                roi_str = grab_in_metrics(r"\bROI\b")
                orders_str = grab_in_metrics(r"\bOrders\b")
                new_cust_str = grab_in_metrics(r"New customers?")
                fee_rate_str = grab(r"Seller fee") if region.upper() == "US" else None

                if not cost_str or not gmv_str:
                    log(f"{region}: failed to extract cost/GMV (attempt {attempt+1})")
                    _ = (browser.close() if browser else ctx.close())
                    time.sleep(15)
                    continue

                bucket = {
                    "region": region.upper(),
                    "month": gap_from[:7],
                    "window_start": gap_from,
                    "window_end": gap_to,
                    "cost": parse_money(cost_str),
                    "currency": "GBP" if region.upper() == "UK" else "USD",
                    "smart_promo_gmv": parse_money(gmv_str),
                    "orders_via_smart_promo": parse_int(orders_str) if orders_str else 0,
                    "new_customers": parse_int(new_cust_str) if new_cust_str else 0,
                    "roi": parse_money(roi_str) if roi_str else 0.0,
                    "source": f"TikTok {region.upper()} Seller Center > Marketing > Smart Promotion",
                    "pulled_at": today.isoformat(),
                }
                if fee_rate_str:
                    bucket["seller_fee_rate"] = parse_money(fee_rate_str)
                _ = (browser.close() if browser else ctx.close())
                return bucket
        except Exception as e:
            log(f"{region}: scrape error (attempt {attempt+1}) -- {e}")
            time.sleep(15)
    return None


def append_bucket(bucket: dict) -> None:
    data: list[dict] = []
    if SMART_PROMO_FILE.exists():
        data = json.loads(SMART_PROMO_FILE.read_text(encoding="utf-8-sig"))
    # Dedup by (region, window_start, window_end) -- never overwrite older buckets
    key = (bucket["region"], bucket["window_start"], bucket["window_end"])
    data = [b for b in data if (b.get("region"), b.get("window_start"), b.get("window_end")) != key]
    data.append(bucket)
    SMART_PROMO_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")


def main() -> int:
    captured = 0
    for region in ("UK", "US"):
        b = capture(region)
        if b is None:
            log(f"{region}: Smart Promo bucket not refreshed -- will retry next refresh")
            continue
        append_bucket(b)
        log(f"{region}: appended bucket {b['window_start']} -> {b['window_end']} "
            f"cost={b['currency']} {b['cost']}")
        captured += 1
    log(f"Smart Promo capture complete: {captured}/2 regions refreshed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
