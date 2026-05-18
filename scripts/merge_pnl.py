"""
merge_pnl.py — Merge Windsor orders + affiliate + ad spend into pnl_daily.json.

Merges:
  - orders_daily from Windsor (order revenue, quantities, cancellations, samples)
  - aff_daily from affiliate CSVs
  - ad_spend_daily + ad_spend_30d from Windsor tiktok connector
  - smart_promo_monthly from data/smart_promo_monthly.json
  - costs_uk / costs_us from data/uk_costs.json / data/us_costs.json
  - monthly_history from data/monthly_history.json (manually maintained)
  - creatives from data/creatives.json (manually maintained, snapshot-based)

Produces: data/pnl_daily.json (same schema as existing project)
"""

import json
import pathlib
from datetime import date

ROOT = pathlib.Path(__file__).resolve().parent.parent


def load_json(path: pathlib.Path, default=None):
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8-sig"))
    return default


def run(
    aff_daily: list[dict],
    orders_daily: list[dict],
    ad_spend_daily: dict,
    ad_spend_30d: dict,
    smart_promo_monthly: list[dict],
    shop_orders_daily: dict | None = None,
) -> dict:
    today = date.today().isoformat()

    # 1) Overlay reference orders_daily for its window (richer SKU-level data
    #    pre-built from Seller Center "All Orders" exports — has real cancellation
    #    /sample/refund splits we can't get from affiliate CSVs alone).
    baseline = load_json(ROOT / "data" / "orders_baseline.json", None)
    overlay_end = None
    if baseline and baseline.get("orders_daily"):
        b_start = baseline["window_start"]
        b_end = baseline["window_end"]
        overlay_end = b_end
        orders_daily = [r for r in orders_daily if not (b_start <= r.get("date", "") <= b_end)]
        orders_daily.extend(baseline["orders_daily"])
        print(f"  Overlay: replaced {b_start}->{b_end} with reference baseline ({len(baseline['orders_daily'])} records)")

    # 2) Top-up: for dates AFTER the overlay window where affiliate CSVs have no
    #    coverage either, inject Windsor tiktok_shop daily totals as single
    #    "(all)" SKU rows per region. This gives the dashboard live numbers for
    #    yesterday/today even when fresh affiliate CSVs haven't been dropped.
    if shop_orders_daily:
        cutoff = overlay_end or "0000-00-00"
        existing_dates = {(r.get("date"), r.get("region")) for r in orders_daily}
        injected = 0
        for day, regions in shop_orders_daily.items():
            if day <= cutoff:
                continue
            for region, b in regions.items():
                # Skip if affiliate CSV already populated this (date, region)
                if (day, region) in existing_dates:
                    continue
                ccy = b.get("currency", "GBP" if region == "UK" else "USD")
                net_orders = b.get("net_orders", 0) or 0
                cancelled = b.get("cancelled_orders", 0) or 0
                orders_daily.append({
                    "date": day, "region": region, "sku": "(all)", "variation": "(all)",
                    "currency": ccy, "is_free_gift": False,
                    "orders": (b.get("orders", 0) or 0),
                    "qty": net_orders,  # approximation: 1 unit / order
                    "return_qty": 0,
                    "gross": b.get("gross", 0) or 0,
                    "plat_disc": b.get("plat_disc", 0) or 0,
                    "seller_disc": b.get("seller_disc", 0) or 0,
                    "net_sku": b.get("sub_total", 0) or 0,
                    "shipping": 0, "tax": 0, "refund": 0,
                    "sales": b.get("net_sales", 0) or 0,
                    "revenue_after_refund": b.get("net_sales", 0) or 0,
                    "return_value": 0,
                    "cancelled_orders": cancelled, "cancelled_qty": cancelled,
                    "cancelled_amt": b.get("cancelled_amt", 0) or 0,
                    "sample_orders": 0, "sample_qty": 0,
                    "net_orders": net_orders, "net_qty": net_orders,
                    "net_gross": b.get("gross", 0) or 0,
                    "net_plat_disc": b.get("plat_disc", 0) or 0,
                    "net_seller_disc": b.get("seller_disc", 0) or 0,
                    "net_sku_total": b.get("sub_total", 0) or 0,
                    "net_shipping": 0, "net_refund": 0,
                    "net_return_qty": 0, "net_return_value": 0,
                    "net_sales": b.get("net_sales", 0) or 0,
                    "order_amt": b.get("total_paid", 0) or 0,
                })
                injected += 1
        if injected:
            print(f"  Windsor top-up: injected {injected} (date, region) rows for dates after {cutoff}")

    # Determine window from orders (per-region and global)
    dates = [r["date"] for r in orders_daily if r.get("date")]
    window_start = min(dates) if dates else today
    window_end = max(dates) if dates else today
    window_days = (date.fromisoformat(window_end) - date.fromisoformat(window_start)).days + 1
    uk_dates = [r["date"] for r in orders_daily if r.get("date") and r.get("region") == "UK"]
    us_dates = [r["date"] for r in orders_daily if r.get("date") and r.get("region") == "US"]
    window_end_uk = max(uk_dates) if uk_dates else window_end
    window_end_us = max(us_dates) if us_dates else window_end

    costs_uk = load_json(ROOT / "data" / "uk_costs.json", {})
    costs_us = load_json(ROOT / "data" / "us_costs.json", {})
    monthly_history = load_json(ROOT / "data" / "monthly_history.json", None)
    creatives = load_json(ROOT / "data" / "creatives.json", None)

    pnl = {
        "pulled_at": today,
        "window_start": window_start,
        "window_end": window_end,
        "window_end_uk": window_end_uk,
        "window_end_us": window_end_us,
        "window_days": window_days,
        "orders_daily": orders_daily,
        "aff_daily": aff_daily,
        "ad_spend_daily": ad_spend_daily,
        "ad_spend_30d": ad_spend_30d,
        "smart_promo_monthly": smart_promo_monthly,
        "costs_uk": costs_uk,
        "costs_us": costs_us,
        "notes": [
            "Orders from Windsor.ai tiktok_shop connector.",
            "Affiliate commissions from manually-exported Seller Center CSVs.",
            "Ad spend from Windsor.ai tiktok connector.",
            "Smart Promotion from manually-entered data/smart_promo_monthly.json.",
            "Monthly history from manually-maintained data/monthly_history.json.",
        ],
    }

    if creatives is not None:
        pnl["creatives"] = creatives
    if monthly_history is not None:
        pnl["monthly_history"] = monthly_history

    out = ROOT / "data" / "pnl_daily.json"
    out.write_text(json.dumps(pnl, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"  Wrote {out} ({out.stat().st_size:,} bytes)")
    print(f"  Window: {window_start} -> {window_end} ({window_days}d)")
    print(f"  Orders: {len(orders_daily)} records")
    print(f"  Affiliate: {len(aff_daily)} records")
    print(f"  Smart promo: {len(smart_promo_monthly)} entries")

    return pnl


if __name__ == "__main__":
    # Standalone: load cached Windsor data and re-merge
    import sys
    sys.path.insert(0, str(ROOT / "scripts"))

    orders = load_json(ROOT / "data" / "windsor_orders.json", [])
    ad_daily = load_json(ROOT / "data" / "windsor_ads_daily.json", {})
    ad_30d = load_json(ROOT / "data" / "windsor_ads_30d.json", {})
    sp = load_json(ROOT / "data" / "smart_promo_monthly.json", [])

    # Re-run affiliate ingestion
    from ingest_seller import run as ingest_run
    aff, _ = ingest_run()

    run(orders, aff, ad_daily, ad_30d, sp)
