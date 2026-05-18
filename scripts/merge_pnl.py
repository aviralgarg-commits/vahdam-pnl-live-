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
    #    coverage either, inject Windsor tiktok_shop daily totals — allocated
    #    across SKU/variation using the historical mix from the last 14 days of
    #    overlay data. This way the per-SKU breakdown table still populates for
    #    yesterday/today instead of showing a single "(all)" row.
    if shop_orders_daily:
        from datetime import timedelta as _td
        cutoff = overlay_end or "0000-00-00"
        cutoff_d = date.fromisoformat(cutoff) if cutoff != "0000-00-00" else None
        existing_dates = {(r.get("date"), r.get("region")) for r in orders_daily}

        # Build (region, sku, variation) -> share of regional net_sales across
        # the last 14 days of overlay data (the SKU-aware reference rows).
        mix_window_start = (cutoff_d - _td(days=13)).isoformat() if cutoff_d else "2000-01-01"
        mix_totals: dict[str, dict[tuple, float]] = {"UK": {}, "US": {}}
        for r in orders_daily:
            d = r.get("date", "")
            if not d or d < mix_window_start or d > cutoff or r.get("is_free_gift"):
                continue
            region = r.get("region")
            if region not in mix_totals:
                continue
            key = (r.get("sku", ""), r.get("variation", ""))
            mix_totals[region][key] = mix_totals[region].get(key, 0.0) + (r.get("net_sales", 0) or 0)
        # Convert each region's mix to shares
        mix_share: dict[str, list[tuple]] = {}
        for region, sk_map in mix_totals.items():
            total = sum(sk_map.values()) or 1.0
            mix_share[region] = sorted(
                ((sku, var, amt / total) for (sku, var), amt in sk_map.items()),
                key=lambda x: -x[2],
            )

        injected = 0
        for day, regions in shop_orders_daily.items():
            if day <= cutoff:
                continue
            for region, b in regions.items():
                if (day, region) in existing_dates:
                    continue
                ccy = b.get("currency", "GBP" if region == "UK" else "USD")
                total_net_orders = b.get("net_orders", 0) or 0
                total_cancelled = b.get("cancelled_orders", 0) or 0
                total_net_sales = b.get("net_sales", 0) or 0
                total_gross = b.get("gross", 0) or 0
                total_plat = b.get("plat_disc", 0) or 0
                total_seller = b.get("seller_disc", 0) or 0
                total_sub = b.get("sub_total", 0) or 0
                total_cancel_amt = b.get("cancelled_amt", 0) or 0
                total_paid = b.get("total_paid", 0) or 0

                buckets = mix_share.get(region, [])
                if not buckets:
                    # No historical data to allocate against — fall back to a single
                    # "(all)" row so the totals still surface in top-line KPIs.
                    buckets = [("(all)", "(all)", 1.0)]

                # Allocate proportionally; track residuals so totals match exactly.
                allocated_orders = 0
                allocated_qty = 0
                allocated_cancelled = 0
                for i, (sku, var, share) in enumerate(buckets):
                    is_last = (i == len(buckets) - 1)
                    if is_last:
                        # Assign the remainder to absorb rounding drift
                        sku_orders = total_net_orders - allocated_orders
                        sku_qty = total_net_orders - allocated_qty  # 1 unit / order approx
                        sku_cancelled = total_cancelled - allocated_cancelled
                    else:
                        sku_orders = int(round(total_net_orders * share))
                        sku_qty = sku_orders
                        sku_cancelled = int(round(total_cancelled * share))
                    allocated_orders += sku_orders
                    allocated_qty += sku_qty
                    allocated_cancelled += sku_cancelled

                    if sku_orders <= 0 and sku_cancelled <= 0:
                        continue

                    orders_daily.append({
                        "date": day, "region": region, "sku": sku, "variation": var,
                        "currency": ccy, "is_free_gift": False,
                        "orders": sku_orders + sku_cancelled,
                        "qty": sku_qty, "return_qty": 0,
                        "gross": round(total_gross * share, 2),
                        "plat_disc": round(total_plat * share, 2),
                        "seller_disc": round(total_seller * share, 2),
                        "net_sku": round(total_sub * share, 2),
                        "shipping": 0, "tax": 0, "refund": 0,
                        "sales": round(total_net_sales * share, 2),
                        "revenue_after_refund": round(total_net_sales * share, 2),
                        "return_value": 0,
                        "cancelled_orders": sku_cancelled, "cancelled_qty": sku_cancelled,
                        "cancelled_amt": round(total_cancel_amt * share, 2),
                        "sample_orders": 0, "sample_qty": 0,
                        "net_orders": sku_orders, "net_qty": sku_qty,
                        "net_gross": round(total_gross * share, 2),
                        "net_plat_disc": round(total_plat * share, 2),
                        "net_seller_disc": round(total_seller * share, 2),
                        "net_sku_total": round(total_sub * share, 2),
                        "net_shipping": 0, "net_refund": 0,
                        "net_return_qty": 0, "net_return_value": 0,
                        "net_sales": round(total_net_sales * share, 2),
                        "order_amt": round(total_paid * share, 2),
                    })
                    injected += 1
        if injected:
            print(f"  Windsor top-up: injected {injected} SKU-allocated rows for dates after {cutoff} (mix from {mix_window_start} -> {cutoff})")

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
