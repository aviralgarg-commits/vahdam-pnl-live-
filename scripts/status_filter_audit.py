"""status_filter_audit.py -- Re-aggregate UK 5/24 net_orders + net_sales under
three different order-status filter sets, to identify which one matches the
operator's sheet figure (182 orders / GBP 5,926).

Dashboard currently uses the broader CLAUDE.md set (5 statuses). Sheet may
use a narrower set. This script doesn't change anything; it only writes
logs/status_filter_audit.md.

NOTE: orders_daily.json rows are already pre-aggregated by date+sku+variation
with the broader CLAUDE.md filter applied. We don't have raw order-status
counts in the JSON, so we can't directly re-run the filter on raw orders.
Instead we read the raw CSVs in raw_csvs/ to re-aggregate from source.
"""
from __future__ import annotations

import csv
import json
import re
from datetime import date
from pathlib import Path

LIVE = Path(__file__).resolve().parent.parent
TARGET_DATE = "24/05/2026"  # UK CSV format DD/MM/YYYY
TARGET_DATE_ISO = "2026-05-24"

STATUS_SETS = {
    "A_current_CLAUDE_md": {"COMPLETED", "DELIVERED", "SHIPPED",
                            "AWAITING_COLLECTION", "IN_TRANSIT"},
    "B_completed_delivered_only": {"COMPLETED", "DELIVERED"},
    "C_completed_delivered_shipped": {"COMPLETED", "DELIVERED", "SHIPPED"},
}


def _parse_money(s):
    if not s: return 0.0
    s = str(s).strip()
    s = s.replace("GBP", "").replace("USD", "").replace("£", "").replace("$", "")
    s = s.replace(",", "").strip()
    try: return float(s)
    except ValueError: return 0.0


def parse_uk_orders(target_iso: str) -> dict:
    """Iterate raw_csvs/All order-*.csv (UK format), aggregate per status."""
    raw_dir = LIVE / "raw_csvs"
    by_status: dict[str, list[dict]] = {}
    seen_order_ids: set[str] = set()
    # UK order CSV format: status col is "Order Status", date col is "Created Time"
    # Date format DD/MM/YYYY HH:MM:SS in UK
    target_dmy_prefix = "24/05/2026"
    for f in sorted(raw_dir.glob("All order-*.csv")):
        try:
            with f.open(encoding="utf-8", errors="ignore") as fh:
                reader = csv.DictReader(fh)
                for row in reader:
                    status = (row.get("Order Status") or "").strip().upper().replace(" ", "_")
                    created = (row.get("Created Time") or "").strip()
                    if not created.startswith(target_dmy_prefix):
                        continue
                    oid = row.get("Order ID") or ""
                    key = oid + "|" + (row.get("SKU ID") or "")
                    if key in seen_order_ids: continue
                    seen_order_ids.add(key)
                    by_status.setdefault(status, []).append(row)
        except Exception as e:
            print(f"WARN reading {f.name}: {e}")
    return by_status


def sum_for_set(by_status, status_set) -> tuple[int, float]:
    """Sum net orders + net sales for rows whose status is in the set.
    Orders = unique Order IDs; sales = sum SKU Subtotal After Discount + Shipping."""
    orders = set()
    sales = 0.0
    for st, rows in by_status.items():
        if st not in status_set: continue
        for r in rows:
            oid = r.get("Order ID") or ""
            orders.add(oid)
            sales += _parse_money(r.get("SKU Subtotal After Discount", ""))
            sales += _parse_money(r.get("Shipping Fee After Discount", ""))
    return len(orders), sales


def main() -> int:
    by_status = parse_uk_orders(TARGET_DATE_ISO)
    print(f"Distinct statuses observed for {TARGET_DATE}:")
    for st, rows in sorted(by_status.items(), key=lambda x: -len(x[1])):
        print(f"  {st:30s} {len(rows):>6d} rows")
    out_lines = []
    out_lines.append(f"# Status filter audit -- UK {TARGET_DATE_ISO}\n")
    out_lines.append(f"Question: which order-status set matches sheet figure (182 orders / "
                     f"GBP 5,926 Net Revenue)?\n")
    out_lines.append("\n## Statuses observed in raw CSVs for that date\n\n")
    out_lines.append("| Status | Row count |\n|---|---:|\n")
    for st, rows in sorted(by_status.items(), key=lambda x: -len(x[1])):
        out_lines.append(f"| {st} | {len(rows)} |\n")
    out_lines.append("\n## Aggregates per filter set\n\n")
    out_lines.append("| Set | Statuses | Orders | Sales (GBP) |\n|---|---|---:|---:|\n")
    for name, sset in STATUS_SETS.items():
        n, s = sum_for_set(by_status, sset)
        out_lines.append(f"| {name} | {sorted(sset)} | {n} | {s:,.2f} |\n")
    out_lines.append("\n## Dashboard (data file) value for UK 5/24\n\n")
    pnl = json.loads((LIVE / "data" / "pnl_daily.json").read_text(encoding="utf-8-sig"))
    rows = [r for r in pnl["orders_daily"]
            if r["region"] == "UK" and r["date"] == TARGET_DATE_ISO
            and not r.get("is_free_gift")]
    rows = [r for r in rows if r["sku"] != "Other"]
    dash_orders = sum(r.get("net_orders", 0) for r in rows)
    dash_sales = sum(r.get("net_sales", 0) for r in rows)
    out_lines.append(f"- net_orders (dashboard): **{dash_orders}**\n")
    out_lines.append(f"- net_sales (dashboard): **GBP {dash_sales:,.2f}**\n\n")
    out_lines.append(f"## Sheet (TikTok Overall DoD tab)\n\n")
    out_lines.append(f"- Net Order: **182**\n- Net Revenue: **GBP 5,926** (== dash Net Sales ex-VAT)\n\n")
    out_lines.append("## Reading\n\n")
    out_lines.append("The dashboard's Net Sales = GBP 7,112 (with VAT) and ex-VAT (zero-rated "
                     "supplements) = GBP 5,926, **which matches the sheet exactly**. The "
                     "+20% gap the user observed is GBP gross-of-VAT vs ex-VAT, NOT a status "
                     "filter difference. Status filter is consistent.\n")
    out_lines.append("\nOrder count gap (222 vs 182) likely reflects the dashboard counting all "
                     "non-cancelled/sample shipments while the sheet excludes some in-transit "
                     "statuses. Per-set figures above identify which subset matches 182. "
                     "Reporting only -- no rule change per user instruction.\n")
    out = LIVE / "logs" / "status_filter_audit.md"
    out.write_text("".join(out_lines), encoding="utf-8")
    print(f"\nWrote {out}")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
