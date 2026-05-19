"""
refresh_daily.py — Orchestrator: Windsor ads -> Affiliate CSVs -> Merge -> Build dashboard.

Run this daily (via Windows Task Scheduler at 7 AM).
Sequence:
  1. fetch_windsor.py  — pull TikTok Ads spend from Windsor.ai
  2. ingest_seller.py  — parse affiliate CSVs from raw_csvs/ (also derives orders_daily)
  3. merge_pnl.py      — combine into data/pnl_daily.json
  4. build_dashboard.py — rebuild public/index.html
"""

import pathlib
import sys
import time
import traceback

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))


def run_step(name: str, fn):
    print(f"\n{'='*60}")
    print(f"STEP: {name}")
    print(f"{'='*60}")
    t0 = time.time()
    try:
        result = fn()
        elapsed = time.time() - t0
        print(f"  OK {name} done in {elapsed:.1f}s")
        return result
    except Exception as e:
        elapsed = time.time() - t0
        print(f"  FAILED {name} in {elapsed:.1f}s: {e}")
        traceback.print_exc()
        return None


def main():
    print("\n" + "=" * 60)
    print("Vahdam P&L Daily Refresh")
    print(f"Time: {__import__('datetime').datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)

    import fetch_windsor
    import ingest_seller
    import merge_pnl
    import fetch_google_sheets
    import scrape_affiliate
    import scrape_smart_promo

    # Step 0: refresh source-of-truth snapshot from live Google Sheets (verifier
    # uses this; no-op if credentials missing).
    run_step("Refresh Google Sheets snapshot", fetch_google_sheets.main)

    # Step 1: Windsor ads + tiktok_shop orders + statement affiliate fees
    windsor_result = run_step("Windsor ads fetch", fetch_windsor.run)

    # Step 1.5: Chrome-driven Seller Center scrapes (idempotent, gracefully fail
    # if Playwright auth missing). These pull data Windsor doesn't expose:
    #   - affiliate orders CSVs (UK + US) — drops new files into raw_csvs/
    #   - Smart Promotion buckets (UK + US) — appends to smart_promo_monthly.json
    run_step("Scrape affiliate CSVs (Seller Center)", scrape_affiliate.main)
    run_step("Scrape Smart Promotion (Seller Center)", scrape_smart_promo.main)
    if windsor_result is None:
        from merge_pnl import load_json
        ad_daily = load_json(ROOT / "data" / "windsor_ads_daily.json", {})
        ad_30d = load_json(ROOT / "data" / "windsor_ads_30d.json", {})
        shop_orders_daily = load_json(ROOT / "data" / "windsor_shop_orders_daily.json", {})
        shop_aff_daily = load_json(ROOT / "data" / "windsor_shop_aff_daily.json", {})
        shop_refunds_daily = load_json(ROOT / "data" / "windsor_shop_refunds_daily.json", {})
    else:
        ad_daily, ad_30d, shop_orders_daily, shop_aff_daily, shop_refunds_daily = windsor_result

    # Step 2: Affiliate ingestion (also derives orders_daily from GMV)
    aff_result = run_step("Affiliate ingestion", ingest_seller.run)
    if aff_result is None:
        aff_daily, orders_daily, smart_promo = [], [], []
    else:
        aff_daily, orders_daily, smart_promo = aff_result

    # Step 3: Merge
    def do_merge():
        return merge_pnl.run(aff_daily, orders_daily, ad_daily, ad_30d, smart_promo,
                             shop_orders_daily, shop_aff_daily)

    run_step("Merge pnl_daily.json", do_merge)

    # Step 4: Build dashboard
    def do_build():
        import importlib
        import build_dashboard
        importlib.reload(build_dashboard)

    run_step("Build dashboard HTML", do_build)

    # Step 5: Reconcile CM1/CM2 against user's source-of-truth spreadsheets
    def do_verify():
        import importlib
        import verify_against_sheets
        importlib.reload(verify_against_sheets)
        return verify_against_sheets.reconcile()

    run_step("Verify against source sheets", do_verify)

    print("\n" + "=" * 60)
    print("Refresh complete. Dashboard: public/index.html")
    print("Server: http://localhost:8000/")
    print("=" * 60)


if __name__ == "__main__":
    main()
