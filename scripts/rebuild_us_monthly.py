"""rebuild_us_monthly.py -- Rebuild monthly_history.US.overall and .products
into the same month-keyed schema UK uses, sourced from the
overall_raw_metric_keyed snapshot (which itself was extracted from the
operator's Google Sheet for Jan-May 2026).

We do NOT aggregate from orders_daily because orders_daily only spans
2026-04-14 to 2026-05-24 -- Jan-Mar would be zero. UK's monthly_history
follows the same convention: monthly values come from the sheet snapshot,
not the daily-rows window. This script just transposes the metric-keyed
array structure into a month-keyed dict, mapping raw labels to the schema
fields the dashboard's `renderMonthlyHistory()` expects.

Schema produced (per month, per user spec):
  net_orders, net_units, net_sales, net_sales_ex_vat (= net_sales for US),
  cancelled, samples, unit_cost, cm1, cm1_pct, aff_comm, ad_spend,
  smart_promo, free_sample_cost, vat_recovery (= 0 for US), cm2, cm2_pct

After running, also calls build_dashboard.py to refresh public/index.html.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

LIVE = Path(__file__).resolve().parent.parent
PNL_PATH = LIVE / "data" / "pnl_daily.json"

MONTH_MAP = {
    "Jan'26": "2026-01",
    "Feb'26": "2026-02",
    "Mar'26": "2026-03",
    "Apr'26": "2026-04",
    "May'26 MTD": "2026-05",
}


def _val(arr, i, default=0):
    if not isinstance(arr, list) or i >= len(arr) or arr[i] is None:
        return default
    return arr[i]


def transform_overall(raw):
    months = raw.get("months") or ["Jan'26", "Feb'26", "Mar'26", "Apr'26", "May'26 MTD"]
    out = {}
    for i, m in enumerate(months):
        key = MONTH_MAP.get(m)
        if key is None:
            continue
        ns = _val(raw.get("Net Revenue"), i)
        cm1 = _val(raw.get("Abs CM1"), i)
        unit_cost = (_val(raw.get("Actual Commission"), i)
                     + _val(raw.get("Other Fix Charges"), i))
        out[key] = {
            "net_orders":        _val(raw.get("Net Order"), i),
            "net_units":         _val(raw.get("Net Unit"), i),
            "net_sales":         ns,
            "net_sales_ex_vat":  ns,  # US has no VAT
            "cancelled":         _val(raw.get("Cancelled"), i),
            "samples":           _val(raw.get("Free Samples"), i),
            "unit_cost":         unit_cost,
            "cm1":               cm1,
            "cm1_pct":           _val(raw.get("CM1 %"), i),
            "aff_comm":          _val(raw.get("Affiliated Commission"), i),
            "ad_spend":          _val(raw.get("Spend"), i),
            "smart_promo":       _val(raw.get("Promotion Fee"), i),
            "free_sample_cost":  _val(raw.get("Free Samples Fix Charges"), i),
            "vat_recovery":      0.0,  # US has no VAT
            "cm2":               _val(raw.get("Abs CM2"), i),
            "cm2_pct":           _val(raw.get("CM2 %"), i),
        }
    return out


def transform_products(products_raw):
    """Per-SKU monthly. Only fields available in raw."""
    out = {}
    if not isinstance(products_raw, dict):
        return out
    for sku, raw in products_raw.items():
        if not isinstance(raw, dict):
            continue
        months = raw.get("months") or ["Jan'26", "Feb'26", "Mar'26", "Apr'26", "May'26 MTD"]
        sku_out = {}
        for i, m in enumerate(months):
            key = MONTH_MAP.get(m)
            if key is None:
                continue
            ns = _val(raw.get("Net Revenue"), i)
            cm1 = _val(raw.get("Abs CM1"), i)
            cm2 = _val(raw.get("Abs CM2"), i)
            sku_out[key] = {
                "net_orders":       _val(raw.get("Net Order"), i),
                "net_units":        _val(raw.get("Net Unit"), i),
                "net_sales":        ns,
                "net_sales_ex_vat": ns,
                "cancelled":        _val(raw.get("Cancelled"), i),
                "samples":          _val(raw.get("Free Samples"), i),
                "cm1":              cm1,
                "cm1_pct":          (cm1 / ns * 100) if ns else 0,
                "ad_spend":         _val(raw.get("Spend"), i),
                "aff_comm":         _val(raw.get("Affiliated Commission"), i),
                "cm2":              cm2,
                "cm2_pct":          (cm2 / ns * 100) if ns else 0,
            }
        out[sku] = sku_out
    return out


def main() -> int:
    print(f"Reading {PNL_PATH}")
    pnl = json.loads(PNL_PATH.read_text(encoding="utf-8-sig"))
    us = (pnl.get("monthly_history") or {}).get("US") or {}
    raw = us.get("overall_raw_metric_keyed") or {}
    if not raw:
        print("ERROR: US.overall_raw_metric_keyed is empty/missing.")
        return 1

    overall_new = transform_overall(raw)
    products_new = transform_products(us.get("products") or {})

    # Preserve original products as products_raw_metric_keyed
    if isinstance(us.get("products"), dict) and "Coffee" in (us.get("products") or {}):
        # Check if products were already in raw metric-keyed format
        sample = us["products"].get("Coffee", {})
        if isinstance(sample, dict) and "Net Revenue" in sample:
            us["products_raw_metric_keyed"] = us["products"]
    us["products"] = products_new
    us["overall"] = overall_new

    print(f"Rebuilt US.overall: {len(overall_new)} months -> {list(overall_new.keys())}")
    print(f"Rebuilt US.products: {len(products_new)} SKUs -> {list(products_new.keys())}")
    print("\nSample US 2026-04 overall:")
    for k, v in overall_new.get("2026-04", {}).items():
        if isinstance(v, float):
            print(f"  {k}: {v:,.2f}")
        else:
            print(f"  {k}: {v}")
    print("\nSample US 2026-05 (MTD) overall:")
    for k, v in overall_new.get("2026-05", {}).items():
        if isinstance(v, float):
            print(f"  {k}: {v:,.2f}")
        else:
            print(f"  {k}: {v}")

    PNL_PATH.write_text(json.dumps(pnl, separators=(",", ":")), encoding="utf-8")
    print(f"\nWrote {PNL_PATH} (size {PNL_PATH.stat().st_size:,} bytes)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
