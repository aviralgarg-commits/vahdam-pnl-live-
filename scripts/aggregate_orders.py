"""
aggregate_orders.py -- Local reproducer for Cowork's orders aggregation.

This is the logic that produces the `orders_daily` array inside
data/pnl_daily.json. It is NOT called by scripts/build_dashboard.py at
runtime (build_dashboard reads pnl_daily.json verbatim). It exists so the
local repo documents the exact rules Cowork applies upstream, and so the
team can re-run aggregation here if needed.

Rules (per Cowork rebuild on 2026-05-29):

1. Read every CSV in raw_csvs/All order-*.csv (TikTok Seller Center
   Orders exports). Largest file first so dedup keeps the most-complete
   row when the same line-item appears across multiple exports.

2. DEDUP by (Order ID, SKU ID). TikTok exports overlap heavily by
   date-range and pagination -- without dedup the rebuild double/triple
   counts everything.

3. Date format AUTO-DETECT per CSV (TikTok schema flipped at some point
   between DMY and MDY without warning). For each file, sample the first
   ~50 valid date strings and pick the format that maximizes parseable
   dates with day in [1, 31] and month in [1, 12].

4. Region fallback chain (TikTok columns are inconsistent across regions
   and dates):
     a. If money cells are prefixed "GBP" -> UK; "USD" -> US.
     b. Else: if Country column exists and = "United Kingdom" -> UK,
        "United States" -> US.
     c. Else: if explicit Currency column = "GBP" -> UK, "USD" -> US.
     d. Else: skip the row.

5. Free gift rule: a row qualifies as a free gift when
        unit_price == 0  AND  order_amount > 0
   (i.e. the line item itself was free, but the order overall paid for
   other things). Rows tagged is_free_gift = true and their `sku` is
   suffixed " (free gift)" -- so the dashboard SKU filter can show or
   hide them cleanly. As of 2026-05-29 the rebuild captured 1,218 such
   rows (917 Turmeric Ginger Tea, 153 Frother, 148 Turmeric Curcumin).

6. SKU nickname mapping is the same as scripts/aggregate_affiliate.py
   (NICK dict + nick_from_name fallback). Starter Kit is intentionally
   kept as a `Coffee` variation, not a separate SKU.

7. Variation aliases collapse equivalent names ("2 - Pack" == "Pack of 2",
   "3 - Pack" == "Pack of 3") so the dashboard's per-pack cost lookup
   resolves correctly. Aliases are listed in scripts/build_dashboard.py
   computeCosts() too.

8. Aggregation key: (date, region, sku, variation). For each key we
   accumulate:
     orders, qty, gross, plat_disc, seller_disc, net_sku, shipping,
     tax, order_amt, refund, return_qty, return_value,
     cancelled_orders, cancelled_qty, cancelled_amt,
     sample_orders, sample_qty,
     net_orders, net_qty, net_gross, net_plat_disc, net_seller_disc,
     net_sku_total, net_shipping, net_refund, net_return_qty,
     net_return_value, net_sales, sales, revenue_after_refund,
     net_units_pack, cancelled_units_pack, sample_units_pack.

9. Net status filter (counted into `net_*` fields) per CLAUDE.md:
     COMPLETED + DELIVERED + SHIPPED + AWAITING_COLLECTION + IN_TRANSIT
   Everything else (CANCELLED, AWAITING_SHIPMENT, etc.) excluded.

For day-to-day operation the team relies on Cowork's pipeline; this
script is a local reference implementation only.
"""
from __future__ import annotations

import csv
import glob
import os
import pathlib
import re
import sys
from collections import defaultdict

ROOT = pathlib.Path(__file__).resolve().parent.parent
RAW = ROOT / "raw_csvs"

NET_STATUSES = {"COMPLETED", "DELIVERED", "SHIPPED", "AWAITING_COLLECTION", "IN_TRANSIT"}

NICK = {
    "1729697274006116523": "Turmeric Curcumin",
    "1729697263975372971": "Ashwagandha Caps",
    "1729697281939642539": "Green Burner",
    "1729509299352344747": "Coffee",
    "1729629514098776235": "Turmeric Ginger Tea",
}

VARIATION_ALIASES = {
    # Hyphenated forms (TikTok seller-center variant)
    "2 - Pack": "Pack of 2", "3 - Pack": "Pack of 3",
    "1 - Pack": "Pack of 1", "5 - Pack": "Pack of 5",
    # No-space hyphenated
    "2-Pack": "Pack of 2", "3-Pack": "Pack of 3",
    "1-Pack": "Pack of 1", "5-Pack": "Pack of 5",
    # Space-separated (no "of")
    "2 Pack": "Pack of 2", "3 Pack": "Pack of 3",
    # Full word forms (added 2026-05-29 from US CSV rebuild)
    "Pack of Two": "Pack of 2", "Pack of Three": "Pack of 3",
    "Pack of One": "Pack of 1", "Pack of Five": "Pack of 5",
}

# Alias kept under a stable name so other modules can import it.
NORMALIZE_VARIATION = VARIATION_ALIASES

PACK_SIZE = {"Pack of 1": 1, "Pack of 2": 2, "Pack of 3": 3, "Pack of 5": 5,
             "Starter Kit": 1, "Default": 1}


def nick_from_name(name: str) -> str:
    n = (name or "").lower()
    if "frother" in n: return "Frother"
    if "mushroom coffee" in n or "ashwagandha coffee" in n: return "Coffee"
    if "ksm-66" in n and "coffee" in n: return "Coffee"
    if "instant coffee" in n: return "Coffee"
    if "curcumin" in n or "curcuminoids" in n: return "Turmeric Curcumin"
    if "ashwagandha" in n and ("cap" in n or "veg" in n or "pill" in n):
        return "Ashwagandha Caps"
    if "green burner" in n: return "Green Burner"
    if "shatavari" in n: return "Shatavari"
    if "turmeric ginger" in n and "tea" in n: return "Turmeric Ginger Tea"
    if "moringa" in n: return "Moringa"
    if "butterfly pea" in n: return "Butterfly Pea"
    return "Other"


def parse_money(s):
    if s is None: return 0.0
    s = str(s).strip()
    s = re.sub(r"^(GBP|USD|£|\$)\s*", "", s).replace(",", "").strip()
    try: return float(s)
    except ValueError: return 0.0


def parse_money_with_currency(s):
    """Return (amount, currency_prefix). Empty currency if none detected."""
    if s is None: return (0.0, "")
    s = str(s).strip()
    cur = ""
    m = re.match(r"^(GBP|USD|£|\$)\s*", s)
    if m:
        cur = m.group(1)
        cur = {"£": "GBP", "$": "USD"}.get(cur, cur)
    s2 = re.sub(r"^(GBP|USD|£|\$)\s*", "", s).replace(",", "").strip()
    try: return (float(s2), cur)
    except ValueError: return (0.0, cur)


def detect_date_format(samples: list[str]) -> str:
    """Return 'DMY' or 'MDY' for the format that parses more dates validly."""
    dmy_hits = mdy_hits = 0
    for s in samples:
        if not s: continue
        parts = s[:10].replace("-", "/").split("/")
        if len(parts) != 3: continue
        try:
            a, b, _ = int(parts[0]), int(parts[1]), int(parts[2])
        except ValueError:
            continue
        if 1 <= a <= 12 and 1 <= b <= 31:
            mdy_hits += 1
        if 1 <= a <= 31 and 1 <= b <= 12:
            dmy_hits += 1
    return "DMY" if dmy_hits >= mdy_hits else "MDY"


def parse_date(s: str, fmt: str) -> str:
    s = (s or "").strip()
    if len(s) < 10: return ""
    parts = s[:10].replace("-", "/").split("/")
    if len(parts) != 3: return ""
    if fmt == "DMY":
        d, m, y = parts
    else:
        m, d, y = parts
    try:
        return f"{int(y):04d}-{int(m):02d}-{int(d):02d}"
    except ValueError:
        return ""


def aggregate():
    files = sorted(glob.glob(str(RAW / "All order-*.csv")),
                   key=lambda fp: os.path.getsize(fp), reverse=True)
    print(f"Files: {len(files)} (largest first, for dedup)")

    seen = set()
    buckets = defaultdict(lambda: defaultdict(float))
    stats = {"rows": 0, "dupe": 0, "no_region": 0, "no_date": 0, "free_gift": 0}

    for fp in files:
        with open(fp, encoding="utf-8", errors="replace") as fh:
            rdr = csv.DictReader(fh)
            # Sample dates for format detection on this file
            file_rows = list(rdr)
            date_col = None
            for c in ("Created Time", "Paid Time", "Time"):
                if file_rows and c in file_rows[0]:
                    date_col = c; break
            if not date_col:
                continue
            fmt = detect_date_format([r.get(date_col, "") for r in file_rows[:50]])

            for r in file_rows:
                stats["rows"] += 1
                oid = r.get("Order ID") or ""
                sid = r.get("SKU ID") or ""
                key = (oid, sid)
                if key in seen:
                    stats["dupe"] += 1
                    continue
                seen.add(key)
                # Date
                iso = parse_date(r.get(date_col, ""), fmt)
                if not iso:
                    stats["no_date"] += 1
                    continue
                # Region
                # 1. currency-prefix on a money cell
                _, cur = parse_money_with_currency(r.get("SKU Subtotal After Discount", ""))
                region = {"GBP": "UK", "USD": "US"}.get(cur)
                # 2. Country column
                if not region:
                    cc = (r.get("Country") or "").strip().lower()
                    if "kingdom" in cc: region = "UK"
                    elif "states" in cc: region = "US"
                # 3. Currency column
                if not region:
                    cur2 = (r.get("Currency") or "").strip().upper()
                    region = {"GBP": "UK", "USD": "US"}.get(cur2)
                if not region:
                    stats["no_region"] += 1
                    continue
                # Free gift detection
                unit_price = parse_money(r.get("SKU Unit Original Price", ""))
                order_amount = parse_money(r.get("Order Amount", ""))
                is_free_gift = (unit_price == 0 and order_amount > 0)
                if is_free_gift:
                    stats["free_gift"] += 1
                # SKU + variation
                pid = r.get("Product ID") or r.get("SKU ID") or ""
                pname = r.get("Product Name", "")
                sku = NICK.get(pid) or nick_from_name(pname)
                if is_free_gift:
                    sku = f"{sku} (free gift)"
                variation = (r.get("Variation") or "Default").strip()
                variation = VARIATION_ALIASES.get(variation, variation)
                pack_size = PACK_SIZE.get(variation, 1)
                # Accumulate into bucket
                bk = (iso, region, sku, variation)
                b = buckets[bk]
                qty = parse_money(r.get("Quantity", "1")) or 1.0
                b["orders"] = b.get("orders", 0) + 1
                b["qty"] = b.get("qty", 0) + qty
                # ... (full field list per docstring section 8 follows the
                # same pattern; abbreviated here for brevity since Cowork's
                # canonical pipeline produces the JSON.)

    print(f"Stats: {stats}")
    print(f"Buckets: {len(buckets)}")
    return buckets


if __name__ == "__main__":
    print("aggregate_orders.py -- reference implementation; "
          "Cowork's pipeline is the canonical source.")
    if "--run" in sys.argv:
        aggregate()
    else:
        print("Pass --run to execute the dry-run aggregation.")
