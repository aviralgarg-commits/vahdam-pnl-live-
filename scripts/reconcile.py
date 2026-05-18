"""
reconcile.py — Side-by-side reconciliation: my dashboard vs reference dashboard.

Window: 2026-04-15 -> 2026-05-14 (L30 ending May 14).
Region: Both, SKU: All, Variation: All, free gifts: OFF, FX: 1.27.

For each metric, prints reference value, my value, delta, delta %, status.
"""
import json
import pathlib
from datetime import date as _date

REF = pathlib.Path(r"C:\Users\Aviral Garg\Downloads\vahdam-pnl-dashboard\data\pnl_daily.json")
MINE = pathlib.Path(r"C:\Users\Aviral Garg\vahdam-pnl-live\data\pnl_daily.json")
WIN_S, WIN_E = "2026-04-15", "2026-05-14"
FX = 1.27

ref = json.loads(REF.read_text(encoding="utf-8-sig"))
mine = json.loads(MINE.read_text(encoding="utf-8-sig"))


def in_win(d):
    return WIN_S <= (d or "") <= WIN_E


def sum_orders(pnl, field, region=None, sku=None, where=None):
    total = 0.0
    for r in pnl.get("orders_daily", []):
        if not in_win(r.get("date")):
            continue
        if not r.get("is_free_gift", False) is False:
            continue
        if region and r.get("region") != region:
            continue
        if sku and r.get("sku") != sku:
            continue
        if where and not where(r):
            continue
        total += r.get(field, 0) or 0
    return total


def sum_aff(pnl, field, region=None):
    total = 0.0
    for r in pnl.get("aff_daily", []):
        if not in_win(r.get("date")):
            continue
        if region and r.get("region") != region:
            continue
        total += r.get(field, 0) or 0
    return total


def sum_ad(pnl, region):
    """Sum daily_region_total for the window."""
    total = 0.0
    drt = pnl.get("ad_spend_daily", {}).get("daily_region_total", {}).get(region, {})
    for day, v in drt.items():
        if in_win(day):
            total += v or 0
    return total


def sum_ad_by_kind(pnl, region):
    """
    Split campaigns into product_gmv_max vs live_gmv_max+auto+other.
    Reference structure: ad_spend_30d.UK.product_gmv_max[].cost + live_gmv_max[].cost.
    """
    a30 = pnl.get("ad_spend_30d", {}).get(region, {})
    prod = sum((c.get("cost", 0) or 0) for c in a30.get("product_gmv_max", []))
    live = sum((c.get("cost", 0) or 0) for c in a30.get("live_gmv_max", []))
    return prod, live


def smart_promo_for_window(pnl, region):
    """Smart promo entries that fall in the window (monthly entries; pro-rate if partial)."""
    total = 0.0
    for e in pnl.get("smart_promo_monthly", []):
        if e.get("region") != region:
            continue
        month = e.get("month") or e.get("period") or e.get("date")  # try common keys
        amt = e.get("amount") or e.get("smart_promo") or 0
        if month and month.startswith("2026-04") or month.startswith("2026-05"):
            total += amt or 0
    return total


# UK VAT-rated SKUs (drop 20% VAT from sales). Coffee drops VAT only from 2026-04-01.
VAT_DROP_SKUS = {"Ashwagandha Caps", "Turmeric Curcumin", "Green Burner"}
def coffee_drops_vat(date_str):
    return (date_str or "") >= "2026-04-01"


def vat_in_sales(pnl, region):
    total = 0.0
    for r in pnl.get("orders_daily", []):
        if not in_win(r.get("date")) or r.get("region") != region:
            continue
        if r.get("is_free_gift"):
            continue
        sku = r.get("sku", "")
        date_str = r.get("date", "")
        if region != "UK":
            continue
        drops = sku in VAT_DROP_SKUS or (sku == "Coffee" and coffee_drops_vat(date_str))
        if drops:
            ns = r.get("net_sales", 0) or 0
            total += ns * (20 / 120)
    return total


def per_order_shipping(pnl, region):
    """UK £1.99/order from 2026-03-01 onwards (per build_dashboard.py)."""
    if region != "UK":
        return 0.0
    total = 0.0
    for r in pnl.get("orders_daily", []):
        if not in_win(r.get("date")) or r.get("region") != "UK":
            continue
        if r.get("is_free_gift"):
            continue
        if (r.get("date") or "") >= "2026-03-01":
            total += (r.get("net_orders", 0) or 0) * 1.99
    return total


def cogs_for_region(pnl, region):
    """Per-unit COGs aggregated from costs_per_pack × net_qty."""
    costs = pnl.get("costs_uk" if region == "UK" else "costs_us", {}).get("costs_per_pack", {})
    total = 0.0
    for r in pnl.get("orders_daily", []):
        if not in_win(r.get("date")) or r.get("region") != region:
            continue
        if r.get("is_free_gift"):
            continue
        sku = r.get("sku", "")
        var = r.get("variation", "")
        per = costs.get(sku, {}).get(var, {})
        cogs = per.get("cogs", 0) or 0
        total += (r.get("net_qty", 0) or 0) * cogs
    return total


def tt_commission_for_region(pnl, region):
    costs = pnl.get("costs_uk" if region == "UK" else "costs_us", {}).get("costs_per_pack", {})
    total = 0.0
    for r in pnl.get("orders_daily", []):
        if not in_win(r.get("date")) or r.get("region") != region:
            continue
        if r.get("is_free_gift"):
            continue
        sku = r.get("sku", "")
        var = r.get("variation", "")
        per = costs.get(sku, {}).get(var, {})
        comm = per.get("commission", 0) or 0
        total += (r.get("net_qty", 0) or 0) * comm
    return total


def total_unit_costs(pnl, region):
    costs = pnl.get("costs_uk" if region == "UK" else "costs_us", {}).get("costs_per_pack", {})
    comps = ["cogs", "commission", "digital_service_fee", "storage", "vat",
             "logistics_duty", "logistics_cost", "fulfillment", "shipping"]
    total = 0.0
    for r in pnl.get("orders_daily", []):
        if not in_win(r.get("date")) or r.get("region") != region:
            continue
        if r.get("is_free_gift"):
            continue
        sku = r.get("sku", "")
        var = r.get("variation", "")
        per = costs.get(sku, {}).get(var, {})
        per_unit = sum((per.get(c, 0) or 0) for c in comps)
        # UK: drop VAT for zero-rated supplements + post-Apr1 Coffee + drop fulfillment? Match build_dashboard logic.
        # For simplicity here, just use full unit cost — close enough for reconciliation.
        total += (r.get("net_qty", 0) or 0) * per_unit
    return total


def row(label, ref_val, my_val, currency="$"):
    delta = my_val - ref_val
    pct = (delta / ref_val * 100) if abs(ref_val) > 0.01 else 0
    if abs(pct) < 1:
        status = "v"
    elif abs(pct) < 5:
        status = "!"
    else:
        status = "X"
    return (label, ref_val, my_val, delta, pct, status, currency)


def print_table(title, rows):
    print(f"\n### {title}")
    print(f"{'Metric':<38} {'Reference':>14} {'Mine':>14} {'Delta':>12} {'Delta%':>8}  Status")
    print("-" * 100)
    for label, ref_v, my_v, delta, pct, status, ccy in rows:
        sym = "GBP" if ccy == "GBP" else "USD"
        print(f"{label:<38} {sym} {ref_v:>10,.0f} {sym} {my_v:>10,.0f} {sym} {delta:>+8,.0f} {pct:>+7.2f}%  {status}")


# === UK ===
uk_rows = []
uk_rows.append(row("Net Sales (top line)",
    sum_orders(ref, "net_sales", "UK"),
    sum_orders(mine, "net_sales", "UK"), "GBP"))
uk_rows.append(row("VAT in Sales (20%)",
    vat_in_sales(ref, "UK"),
    vat_in_sales(mine, "UK"), "GBP"))
uk_rows.append(row("Net Sales ex-VAT",
    sum_orders(ref, "net_sales", "UK") - vat_in_sales(ref, "UK"),
    sum_orders(mine, "net_sales", "UK") - vat_in_sales(mine, "UK"), "GBP"))
uk_rows.append(row("Net Orders",
    sum_orders(ref, "net_orders", "UK"),
    sum_orders(mine, "net_orders", "UK"), "GBP"))
uk_rows.append(row("Net Units",
    sum_orders(ref, "net_qty", "UK"),
    sum_orders(mine, "net_qty", "UK"), "GBP"))
uk_rows.append(row("Cancelled Orders",
    sum_orders(ref, "cancelled_orders", "UK"),
    sum_orders(mine, "cancelled_orders", "UK"), "GBP"))
uk_rows.append(row("Cancelled Value",
    sum_orders(ref, "cancelled_amt", "UK"),
    sum_orders(mine, "cancelled_amt", "UK"), "GBP"))
uk_rows.append(row("Sample Orders",
    sum_orders(ref, "sample_orders", "UK"),
    sum_orders(mine, "sample_orders", "UK"), "GBP"))
uk_rows.append(row("Sample Units",
    sum_orders(ref, "sample_qty", "UK"),
    sum_orders(mine, "sample_qty", "UK"), "GBP"))
uk_rows.append(row("Refunds",
    sum_orders(ref, "refund", "UK"),
    sum_orders(mine, "refund", "UK"), "GBP"))
uk_rows.append(row("COGs total",
    cogs_for_region(ref, "UK"),
    cogs_for_region(mine, "UK"), "GBP"))
uk_rows.append(row("TT Commission total",
    tt_commission_for_region(ref, "UK"),
    tt_commission_for_region(mine, "UK"), "GBP"))
uk_rows.append(row("Total unit costs",
    total_unit_costs(ref, "UK"),
    total_unit_costs(mine, "UK"), "GBP"))
ref_cm1 = (sum_orders(ref, "net_sales", "UK") - vat_in_sales(ref, "UK")) - total_unit_costs(ref, "UK") - per_order_shipping(ref, "UK")
my_cm1 = (sum_orders(mine, "net_sales", "UK") - vat_in_sales(mine, "UK")) - total_unit_costs(mine, "UK") - per_order_shipping(mine, "UK")
uk_rows.append(row("CM1 (approx)", ref_cm1, my_cm1, "GBP"))
uk_rows.append(row("Affiliate Commission",
    sum_aff(ref, "aff_commission", "UK"),
    sum_aff(mine, "aff_commission", "UK"), "GBP"))
ref_prod, ref_live = sum_ad_by_kind(ref, "UK")
my_prod, my_live = sum_ad_by_kind(mine, "UK")
uk_rows.append(row("Ad Spend Product GMV Max (raw)", ref_prod, my_prod, "GBP"))
uk_rows.append(row("Ad Spend LIVE+Auto (raw)", ref_live, my_live, "GBP"))
uk_rows.append(row("Ad Spend total (raw)",
    ref_prod + ref_live,
    my_prod + my_live, "GBP"))
uk_rows.append(row("Ad Spend total (x1.20 VAT-incl)",
    (ref_prod + ref_live) * 1.20,
    (my_prod + my_live) * 1.20, "GBP"))
uk_rows.append(row("Smart Promotion (raw, monthly)",
    smart_promo_for_window(ref, "UK"),
    smart_promo_for_window(mine, "UK"), "GBP"))

print_table("UK metrics — Window 2026-04-15 -> 2026-05-14", uk_rows)


# === US ===
us_rows = []
us_rows.append(row("Net Sales (top line)",
    sum_orders(ref, "net_sales", "US"),
    sum_orders(mine, "net_sales", "US"), "USD"))
us_rows.append(row("Net Orders",
    sum_orders(ref, "net_orders", "US"),
    sum_orders(mine, "net_orders", "US"), "USD"))
us_rows.append(row("Net Units",
    sum_orders(ref, "net_qty", "US"),
    sum_orders(mine, "net_qty", "US"), "USD"))
us_rows.append(row("Cancelled Orders",
    sum_orders(ref, "cancelled_orders", "US"),
    sum_orders(mine, "cancelled_orders", "US"), "USD"))
us_rows.append(row("Cancelled Value",
    sum_orders(ref, "cancelled_amt", "US"),
    sum_orders(mine, "cancelled_amt", "US"), "USD"))
us_rows.append(row("Sample Orders",
    sum_orders(ref, "sample_orders", "US"),
    sum_orders(mine, "sample_orders", "US"), "USD"))
us_rows.append(row("Refunds",
    sum_orders(ref, "refund", "US"),
    sum_orders(mine, "refund", "US"), "USD"))
us_rows.append(row("COGs total",
    cogs_for_region(ref, "US"),
    cogs_for_region(mine, "US"), "USD"))
us_rows.append(row("TT Commission total",
    tt_commission_for_region(ref, "US"),
    tt_commission_for_region(mine, "US"), "USD"))
us_rows.append(row("Total unit costs",
    total_unit_costs(ref, "US"),
    total_unit_costs(mine, "US"), "USD"))
us_cm1_ref = sum_orders(ref, "net_sales", "US") - total_unit_costs(ref, "US")
us_cm1_my = sum_orders(mine, "net_sales", "US") - total_unit_costs(mine, "US")
us_rows.append(row("CM1 (approx)", us_cm1_ref, us_cm1_my, "USD"))
us_rows.append(row("Affiliate Commission",
    sum_aff(ref, "aff_commission", "US"),
    sum_aff(mine, "aff_commission", "US"), "USD"))
us_prod_r, us_live_r = sum_ad_by_kind(ref, "US")
us_prod_m, us_live_m = sum_ad_by_kind(mine, "US")
us_rows.append(row("Ad Spend Product GMV Max", us_prod_r, us_prod_m, "USD"))
us_rows.append(row("Ad Spend LIVE+Auto", us_live_r, us_live_m, "USD"))
us_rows.append(row("Ad Spend total", us_prod_r + us_live_r, us_prod_m + us_live_m, "USD"))
us_rows.append(row("Smart Promotion (monthly)",
    smart_promo_for_window(ref, "US"),
    smart_promo_for_window(mine, "US"), "USD"))

print_table("US metrics — Window 2026-04-15 -> 2026-05-14", us_rows)

# === Per-SKU Net Sales ===
print("\n\n### Per-SKU Net Sales (UK)")
for sku in ["Coffee", "Turmeric Curcumin", "Ashwagandha Caps", "Green Burner", "Turmeric Ginger Tea", "Shatavari"]:
    r = sum_orders(ref, "net_sales", "UK", sku)
    m = sum_orders(mine, "net_sales", "UK", sku)
    pct = ((m - r) / r * 100) if abs(r) > 0.01 else 0
    print(f"  {sku:<25} ref GBP {r:>10,.0f}  mine GBP {m:>10,.0f}  ({pct:+.2f}%)")

print("\n### Per-SKU Net Sales (US)")
for sku in ["Coffee", "Turmeric Curcumin", "Ashwagandha Caps", "Green Burner", "Turmeric Ginger Tea", "Shatavari"]:
    r = sum_orders(ref, "net_sales", "US", sku)
    m = sum_orders(mine, "net_sales", "US", sku)
    pct = ((m - r) / r * 100) if abs(r) > 0.01 else 0
    print(f"  {sku:<25} ref USD {r:>10,.0f}  mine USD {m:>10,.0f}  ({pct:+.2f}%)")
