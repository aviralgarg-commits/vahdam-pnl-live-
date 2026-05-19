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
    shop_aff_daily: dict | None = None,
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
        # Normalisation pass on overlay rows before extending:
        #  - "Coffee" + "Starter Kit" variation -> SKU "Coffee Starter Kit", variation "Default"
        #    (Starter Kit is a separate SKU listing on TikTok, not a Coffee variation)
        #  - Frother (free gift) rows before 2026-05-13 are dropped (Frother promo
        #    launched 2026-05-13 on min spend £68.99; earlier rows are UTC/BST
        #    boundary artefacts in the upstream CSV)
        FROTHER_LAUNCH = "2026-05-13"
        cleaned = []
        normalised_sk = dropped_frother = 0
        for row in baseline["orders_daily"]:
            r = dict(row)
            if r.get("sku") == "Coffee" and r.get("variation") == "Starter Kit":
                r["sku"] = "Coffee Starter Kit"
                r["variation"] = "Default"
                normalised_sk += 1
            sku = r.get("sku", "")
            if ("Frother" in sku) and (r.get("date", "") < FROTHER_LAUNCH):
                dropped_frother += 1
                continue
            cleaned.append(r)
        orders_daily.extend(cleaned)
        msg = f"  Overlay: replaced {b_start}->{b_end} with reference baseline ({len(cleaned)} records)"
        if normalised_sk: msg += f", normalised {normalised_sk} 'Coffee/Starter Kit' rows -> 'Coffee Starter Kit' SKU"
        if dropped_frother: msg += f", dropped {dropped_frother} Frother rows pre-{FROTHER_LAUNCH}"
        print(msg)

    # 2) Top-up: for ANY (date, region) where the overlay+CSVs have no rows,
    #    inject Windsor tiktok_shop daily totals — allocated across SKU/variation
    #    using the historical mix from the last 14 days of overlay data, with a
    #    per-(sku, variation) units/orders multiplier so net_qty isn't undercounted.
    if shop_orders_daily:
        from datetime import timedelta as _td
        # Set of (date, region) keys that already have at least one row
        existing_keys = {(r.get("date"), r.get("region")) for r in orders_daily
                         if r.get("date") and r.get("region")}

        # Mix + units-per-order multiplier from last 14 days of overlay-window data
        cutoff_d = date.fromisoformat(overlay_end) if overlay_end else None
        mix_window_start = (cutoff_d - _td(days=13)).isoformat() if cutoff_d else "2000-01-01"
        mix_totals: dict[str, dict[tuple, float]] = {"UK": {}, "US": {}}
        upo_orders: dict[str, dict[tuple, int]] = {"UK": {}, "US": {}}
        upo_qty: dict[str, dict[tuple, float]] = {"UK": {}, "US": {}}
        for r in orders_daily:
            d = r.get("date", "")
            if not d or d < mix_window_start or (overlay_end and d > overlay_end) or r.get("is_free_gift"):
                continue
            region = r.get("region")
            if region not in mix_totals:
                continue
            sku = r.get("sku", "")
            var = r.get("variation", "")
            # Don't allocate Windsor totals to SKUs that historically had near-zero
            # revenue (e.g. Starter Kit was rare — allocator was creating £0 phantom
            # rows). Exclude any (sku, variation) that contributed less than £100
            # historically OR has 0 net_orders.
            if (r.get("net_orders", 0) or 0) == 0:
                continue
            key = (sku, var)
            mix_totals[region][key] = mix_totals[region].get(key, 0.0) + (r.get("net_sales", 0) or 0)
            upo_orders[region][key] = upo_orders[region].get(key, 0) + (r.get("net_orders", 0) or 0)
            upo_qty[region][key] = upo_qty[region].get(key, 0.0) + (r.get("net_qty", 0) or 0)
        # Drop any (sku, variation) keys with negligible historical revenue (< £100)
        # so the allocator doesn't create phantom £0 rows on new dates.
        for region in mix_totals:
            mix_totals[region] = {k: v for k, v in mix_totals[region].items() if v >= 100}
            upo_orders[region] = {k: v for k, v in upo_orders[region].items() if k in mix_totals[region]}
            upo_qty[region] = {k: v for k, v in upo_qty[region].items() if k in mix_totals[region]}

        mix_share: dict[str, list[tuple]] = {}
        for region, sk_map in mix_totals.items():
            total = sum(sk_map.values()) or 1.0
            mix_share[region] = sorted(
                ((sku, var, amt / total) for (sku, var), amt in sk_map.items()),
                key=lambda x: -x[2],
            )

        def units_per_order(region: str, sku: str, var: str) -> float:
            """Average units per net order for this region+sku+variation from history."""
            o = upo_orders.get(region, {}).get((sku, var), 0)
            q = upo_qty.get(region, {}).get((sku, var), 0.0)
            if o > 0 and q > 0:
                return q / o
            # Fallback: regional avg
            ro = sum(upo_orders.get(region, {}).values())
            rq = sum(upo_qty.get(region, {}).values())
            return rq / ro if ro > 0 else 1.0

        # Per-region availability of Windsor shop orders
        windsor_uk_dates = {d for d, regs in shop_orders_daily.items() if "UK" in regs}
        windsor_us_dates = {d for d, regs in shop_orders_daily.items() if "US" in regs}

        injected = 0
        for day, regions in shop_orders_daily.items():
            for region, b in regions.items():
                if (day, region) in existing_keys:
                    continue  # overlay/CSV already populated this date
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

                buckets = mix_share.get(region, []) or [("(all)", "(all)", 1.0)]

                allocated_orders = 0
                allocated_cancelled = 0
                # Compute target total qty so allocated rows sum to it
                target_total_qty = int(round(sum(
                    units_per_order(region, sku, var) * total_net_orders * share
                    for sku, var, share in buckets
                )))
                allocated_qty = 0
                for i, (sku, var, share) in enumerate(buckets):
                    is_last = (i == len(buckets) - 1)
                    upo = units_per_order(region, sku, var)
                    if is_last:
                        sku_orders = total_net_orders - allocated_orders
                        sku_qty = target_total_qty - allocated_qty
                        sku_cancelled = total_cancelled - allocated_cancelled
                    else:
                        sku_orders = int(round(total_net_orders * share))
                        sku_qty = int(round(sku_orders * upo))
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
            print(f"  Windsor top-up: injected {injected} SKU-allocated rows (any (date, region) "
                  f"not covered by overlay/CSV); units/order multiplier from {mix_window_start}->{overlay_end}")

    # 3) Affiliate commission top-up from Windsor Statement table (settled-only).
    #    Fresh affiliate CSVs land via scripts/scrape_affiliate.py (Chrome-driven
    #    Seller Center download) — NOT from any snapshot of the user's
    #    verification sheet (that would create a circular dependency).
    if shop_aff_daily:
        existing_aff_keys = {(r.get("date"), r.get("region")) for r in aff_daily
                             if r.get("date") and r.get("region")}
        # Also dedup against rows that have positive aff_commission already
        aff_topup = 0
        for day, regions in shop_aff_daily.items():
            for region, amt in regions.items():
                if (day, region) in existing_aff_keys:
                    continue
                if amt <= 0:
                    continue
                aff_daily.append({
                    "date": day, "region": region, "sku": "(all)",
                    "aff_orders": 0,
                    "aff_revenue": 0.0,
                    "aff_commission": round(amt, 2),
                    "aff_std": 0.0,
                    "aff_shop_ads": round(amt, 2),
                    "aff_co_funded": 0.0,
                    "_source": "windsor_statement",
                })
                aff_topup += 1
        if aff_topup:
            print(f"  Affiliate top-up from Windsor Statement: {aff_topup} (date, region) rows added")

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
