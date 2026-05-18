"""
ingest_seller.py — Parse affiliate CSVs + smart promo data from manual Seller Center exports.

Column layout (index-based, matches actual TikTok Seller Center export format):
  UK CSVs have 31 columns (has "Creator Region" at col 12).
  US CSVs have 30 columns (no "Creator Region").
  Offset = 0 for UK, -1 for US.

  Col  0: Order ID
  Col  1: Product ID
  Col  2: Product Name
  Col  3: SKU ID
  Col  4: Price
  Col  5: Payment Amount   <- GMV / order value
  Col  6: Currency         <- GBP=UK, USD=US
  Col  7: Quantity
  Col  8: Fully returned or refunded
  Col  9: Payment method
  Col 10: Order Status
  Col 11: Creator Username
  [Col 12: Creator Region  <- UK only]
  Col 12+off: Content Type
  ...
  Col 18+off: Est. standard commission payment
  Col 20+off: Actual Commission Payment
  Col 22+off: Est. Shop Ads commission payment
  Col 23+off: Actual Shop Ads commission payment
  Col 24+off: Est. co-funded creator bonus
  Col 25+off: Actual co-funded creator bonus
  Col 26+off: Time Created             <- date column (DD/MM/YYYY)

Rules (NON-NEGOTIABLE from CLAUDE.md):
  - Date: DD/MM/YYYY in "Time Created" column
  - Region: GBP=UK, USD=US (from Currency column)
  - Total commission = Standard + Shop Ads + Co-funded creator bonus
  - Use Actual if > 0, else Estimated (per component)
  - Exclude Order Status = "Ineligible"
  - Deduplicate by Order ID to avoid double-counting duplicate CSV files
"""

import csv
import json
import pathlib
import re
from collections import defaultdict
from datetime import datetime

ROOT = pathlib.Path(__file__).resolve().parent.parent
RAW_CSVS = ROOT / "raw_csvs"
SMART_PROMO_FILE = ROOT / "data" / "smart_promo_monthly.json"

# Product ID -> SKU nickname (fast-path before name matching)
PRODUCT_ID_NICK = {
    "1729697274006116523": "Turmeric Curcumin",
    "1729697263975372971": "Ashwagandha Caps",
    "1729697281939642539": "Green Burner",
    "1729509299352344747": "Coffee",
    "1729629514098776235": "Turmeric Ginger Tea",
}

# TikTok SKU ID -> variation name (Pack of 1/2/3/5).
# Each TikTok SKU ID is unique per variation. Inferred from price tiers across all CSVs.
# Add new SKU IDs here when new product listings appear.
SKU_ID_VARIATION: dict[str, str] = {
    # ── UK (GBP) ──────────────────────────────────────────────────────────────
    # Ashwagandha Caps
    "1729735803858294955": "Pack of 1",
    "1729735803858360491": "Pack of 1",
    "1729768172191258795": "Pack of 2",
    # Turmeric Curcumin
    "1729735804972079275": "Pack of 1",
    "1729735804972144811": "Pack of 2",
    "1729768172153182379": "Pack of 3",
    # Green Burner
    "1729723796674353323": "Pack of 1",
    "1729723796674418859": "Pack of 2",
    # Coffee (KSM-66 Ashwagandha Coffee)
    "1729581609641744555": "Pack of 1",
    "1729829062319577259": "Pack of 1",
    "1729581609641810091": "Pack of 2",
    "1729636075899295915": "Pack of 3",
    "1729812118344013995": "Pack of 5",   # avg GBP 68, 133 orders
    # Green Burner (3rd tier)
    "1729827951823329451": "Pack of 3",
    # Turmeric Ginger Tea
    "1729629542578690219": "Pack of 1",
    "1729629542578755755": "Pack of 2",
    # ── US (USD) ──────────────────────────────────────────────────────────────
    # Ashwagandha Caps
    "1732069589544964273": "Pack of 1",
    "1732069589545029809": "Pack of 2",
    "1729499091546576049": "Pack of 2",
    # Coffee (KSM-66 Ashwagandha Coffee)
    "1730881470376939697": "Pack of 1",
    "1730881470377005233": "Pack of 2",
    "1731088385812107441": "Pack of 3",
    "1732351510015479985": "Pack of 5",   # avg USD 39, 62 orders
    # Turmeric Curcumin
    "1731877424524333233": "Pack of 1",
    "1731877424524398769": "Pack of 2",
    "1732320403761172657": "Pack of 2",
    "1729488250396120241": "Pack of 3",
    "1732360993097224369": "Pack of 5",   # avg USD 39, 31 orders
    # Turmeric Ginger Tea
    "1732069652443336881": "Pack of 1",
    "1732069652443402417": "Pack of 2",
    # Moringa
    "1732110006948630705": "Pack of 1",
    "1732110006948696241": "Pack of 2",
    # Shatavari
    "1732109959987564721": "Pack of 1",
    "1732109959987630257": "Pack of 1",
}


def nick_from_name(product_name: str) -> str:
    """Map product name -> SKU nickname. Priority order is NON-NEGOTIABLE (CLAUDE.md)."""
    n = (product_name or "").lower()
    if "frother" in n:
        return "Frother (free gift)"
    if "butterfly pea" in n:
        return "Butterfly Pea Tea (free gift)"
    if "mushroom coffee" in n:
        return "Coffee"
    if "ashwagandha coffee" in n:
        return "Coffee"
    if ("ksm-66" in n or "ksm66" in n) and "coffee" in n:
        return "Coffee"
    if "instant coffee" in n:
        return "Coffee"
    if "coffee" in n:
        return "Coffee"
    if "curcumin" in n or "curcuminoids" in n:
        return "Turmeric Curcumin"
    if "ashwagandha" in n and ("cap" in n or "veg" in n or "pill" in n or "tablet" in n):
        return "Ashwagandha Caps"
    if "green burner" in n:
        return "Green Burner"
    if "shatavari" in n:
        return "Shatavari"
    if "turmeric" in n and "ginger" in n and "tea" in n:
        return "Turmeric Ginger Tea"
    if "moringa" in n:
        return "Moringa"
    return "Unknown"


def _flt(s: str) -> float:
    try:
        return float(str(s).strip().replace(",", "").replace("£", "").replace("$", ""))
    except (ValueError, AttributeError):
        return 0.0


def parse_date(s: str) -> str:
    """DD/MM/YYYY [HH:MM:SS] -> YYYY-MM-DD. Returns '' on failure."""
    s = (s or "").strip()
    m = re.match(r"(\d{1,2})/(\d{1,2})/(\d{4})", s)
    if m:
        dd, mm, yyyy = m.group(1), m.group(2), m.group(3)
        try:
            return datetime(int(yyyy), int(mm), int(dd)).strftime("%Y-%m-%d")
        except ValueError:
            return ""
    # Fallback: YYYY-MM-DD
    m2 = re.match(r"(\d{4})-(\d{2})-(\d{2})", s)
    if m2:
        return m2.group(0)
    return ""


def parse_all_csvs() -> list[dict]:
    """
    Parse all affiliate_orders_*.csv files in raw_csvs/.
    NO Order ID dedup (matches reference aggregate_affiliate.py — each row is one event).
    Returns list of raw row dicts.
    """
    all_rows: list[dict] = []
    csv_files = sorted(RAW_CSVS.glob("affiliate_orders_*.csv"))
    print(f"\n=== Affiliate ingestion: {len(csv_files)} CSVs ===")

    for fp in csv_files:
        file_rows = 0
        file_skipped = 0
        try:
            with open(fp, encoding="utf-8-sig", errors="replace", newline="") as fh:
                reader = csv.reader(fh)
                try:
                    headers = next(reader)
                except StopIteration:
                    continue

                if len(headers) < 28:
                    print(f"  {fp.name}: skipped (only {len(headers)} headers)")
                    continue

                has_creator_region = "Creator Region" in headers
                off = 0 if has_creator_region else -1

                IDX_TIME = 26 + off
                IDX_STD_EST = 18 + off
                IDX_STD_ACT = 20 + off
                IDX_SA_EST  = 22 + off
                IDX_SA_ACT  = 23 + off
                IDX_CF_EST  = 24 + off
                IDX_CF_ACT  = 25 + off

                for row in reader:
                    if len(row) < 26 + off:
                        continue

                    status = row[10].strip() if len(row) > 10 else ""
                    if status.lower() == "ineligible":
                        file_skipped += 1
                        continue

                    date_str = parse_date(row[IDX_TIME] if len(row) > IDX_TIME else "")
                    if not date_str:
                        file_skipped += 1
                        continue

                    currency = row[6].strip() if len(row) > 6 else ""
                    if currency == "GBP":
                        region = "UK"
                    elif currency == "USD":
                        region = "US"
                    else:
                        file_skipped += 1
                        continue

                    product_id = row[1].strip() if len(row) > 1 else ""
                    product_name = row[2].strip() if len(row) > 2 else ""
                    sku_id = row[3].strip() if len(row) > 3 else ""
                    sku = PRODUCT_ID_NICK.get(product_id) or nick_from_name(product_name)
                    variation = SKU_ID_VARIATION.get(sku_id, "Pack of 1")

                    qty = max(1, int(_flt(row[7] if len(row) > 7 else "1") or 1))
                    price = _flt(row[4] if len(row) > 4 else "0")
                    gmv = _flt(row[5] if len(row) > 5 else "0")
                    returned_flag = (row[8].strip().lower() == "yes") if len(row) > 8 else False

                    # Categorise: cancelled / sample (pmt=0) / returned / normal
                    is_cancelled = status.lower() in ("cancelled", "cancel", "canceled")
                    is_sample = (not is_cancelled) and (gmv <= 0)
                    is_returned = returned_flag and not is_cancelled

                    std_est = _flt(row[IDX_STD_EST] if len(row) > IDX_STD_EST else "0")
                    std_act = _flt(row[IDX_STD_ACT] if len(row) > IDX_STD_ACT else "0")
                    sa_est  = _flt(row[IDX_SA_EST]  if len(row) > IDX_SA_EST  else "0")
                    sa_act  = _flt(row[IDX_SA_ACT]  if len(row) > IDX_SA_ACT  else "0")
                    cf_est  = _flt(row[IDX_CF_EST]  if len(row) > IDX_CF_EST  else "0")
                    cf_act  = _flt(row[IDX_CF_ACT]  if len(row) > IDX_CF_ACT  else "0")

                    std = std_act if std_act > 0 else std_est
                    sa  = sa_act  if sa_act  > 0 else sa_est
                    cf  = cf_act  if cf_act  > 0 else cf_est

                    file_rows += 1
                    all_rows.append({
                        "date":           date_str,
                        "region":         region,
                        "sku":            sku,
                        "variation":      variation,
                        "qty":            qty,
                        "price":          price,
                        "is_cancelled":   is_cancelled,
                        "is_sample":      is_sample,
                        "is_returned":    is_returned,
                        "order_status":   status,
                        "aff_revenue":    round(gmv, 2),
                        "aff_std":        round(std, 2),
                        "aff_shop_ads":   round(sa, 2),
                        "aff_co_funded":  round(cf, 2),
                        "aff_commission": round(std + sa + cf, 2),
                    })

            region_str = "UK" if any(r["region"] == "UK" for r in all_rows[-file_rows:]) else "US"
            print(f"  {fp.name}: {file_rows} rows ({region_str}), {file_skipped} skipped")
        except Exception as e:
            print(f"  {fp.name}: ERROR -- {e}")

    return all_rows


def aggregate_aff_daily(rows: list[dict]) -> list[dict]:
    """Group by (date, region, sku) -> aff_daily records."""
    buckets: dict[tuple, dict] = {}
    for r in rows:
        key = (r["date"], r["region"], r["sku"])
        if key not in buckets:
            buckets[key] = {
                "date": r["date"], "region": r["region"], "sku": r["sku"],
                "aff_orders": 0, "aff_revenue": 0.0, "aff_commission": 0.0,
                "aff_std": 0.0, "aff_shop_ads": 0.0, "aff_co_funded": 0.0,
            }
        b = buckets[key]
        b["aff_orders"] += 1
        b["aff_revenue"] += r["aff_revenue"]
        b["aff_commission"] += r["aff_commission"]
        b["aff_std"] += r["aff_std"]
        b["aff_shop_ads"] += r["aff_shop_ads"]
        b["aff_co_funded"] += r["aff_co_funded"]
    return list(buckets.values())


def aggregate_orders_daily(rows: list[dict]) -> list[dict]:
    """
    Group by (date, region, sku, variation) -> orders_daily records.
    Each row in the input is one affiliate order line. Categorise into:
      - cancelled (Order Status = Cancelled)
      - sample (Payment Amount = 0, not cancelled)
      - returned (Fully returned/refunded = Yes, not cancelled)
      - normal (everything else)
    net_* fields exclude cancelled + samples.
    """
    free_gift_skus = {"Frother (free gift)", "Butterfly Pea Tea (free gift)"}
    buckets: dict[tuple, dict] = {}
    for r in rows:
        key = (r["date"], r["region"], r["sku"], r["variation"])
        if key not in buckets:
            ccy = "GBP" if r["region"] == "UK" else "USD"
            buckets[key] = {
                "date": r["date"], "region": r["region"], "sku": r["sku"],
                "variation": r["variation"],
                "currency": ccy, "is_free_gift": r["sku"] in free_gift_skus,
                "orders": 0, "qty": 0, "return_qty": 0,
                "gross": 0.0, "plat_disc": 0.0, "seller_disc": 0.0,
                "net_sku": 0.0, "shipping": 0.0, "tax": 0.0, "refund": 0.0,
                "sales": 0.0, "revenue_after_refund": 0.0, "return_value": 0.0,
                "cancelled_orders": 0, "cancelled_qty": 0, "cancelled_amt": 0.0,
                "sample_orders": 0, "sample_qty": 0,
                "net_orders": 0, "net_qty": 0,
                "net_gross": 0.0, "net_plat_disc": 0.0, "net_seller_disc": 0.0,
                "net_sku_total": 0.0, "net_shipping": 0.0, "net_refund": 0.0,
                "net_return_qty": 0, "net_return_value": 0.0,
                "net_sales": 0.0, "order_amt": 0.0,
            }
        b = buckets[key]
        qty = r.get("qty", 1)
        price = r.get("price", 0.0)
        gmv = r["aff_revenue"]
        line_gross = price * qty if price > 0 else gmv
        # Total discount (we can't separate platform vs seller from affiliate CSV — put it all in seller_disc)
        line_disc = max(0.0, line_gross - gmv)

        # All-status totals
        b["orders"] += 1
        b["qty"] += qty
        b["gross"] += line_gross
        b["seller_disc"] += line_disc
        b["net_sku"] += gmv  # price-after-discount, before refund
        b["order_amt"] += gmv
        b["sales"] += gmv
        b["revenue_after_refund"] += gmv

        if r["is_cancelled"]:
            b["cancelled_orders"] += 1
            b["cancelled_qty"] += qty
            b["cancelled_amt"] += gmv
        elif r["is_sample"]:
            b["sample_orders"] += 1
            b["sample_qty"] += qty
        else:
            # Net order (excluding cancelled + samples)
            b["net_orders"] += 1
            b["net_qty"] += qty
            b["net_gross"] += line_gross
            b["net_seller_disc"] += line_disc
            b["net_sku_total"] += gmv
            b["net_sales"] += gmv
            if r["is_returned"]:
                b["net_return_qty"] += qty
                b["net_return_value"] += gmv
                b["net_refund"] += gmv
                b["return_qty"] += qty
                b["return_value"] += gmv
                b["refund"] += gmv
    return list(buckets.values())


def run() -> tuple[list[dict], list[dict], list[dict]]:
    """
    Parse all affiliate CSVs. Returns (aff_daily, orders_daily, smart_promo_monthly).
    """
    all_rows = parse_all_csvs()

    aff_daily = aggregate_aff_daily(all_rows)
    orders_daily = aggregate_orders_daily(all_rows)

    uk_rev = sum(r["aff_revenue"] for r in all_rows if r["region"] == "UK")
    us_rev = sum(r["aff_revenue"] for r in all_rows if r["region"] == "US")
    uk_comm = sum(r["aff_commission"] for r in all_rows if r["region"] == "UK")
    us_comm = sum(r["aff_commission"] for r in all_rows if r["region"] == "US")

    print(f"  -> {len(aff_daily)} aff_daily, {len(orders_daily)} orders_daily records")
    print(f"  UK GMV: £{uk_rev:,.0f} | UK Commission: £{uk_comm:,.0f}")
    print(f"  US GMV: ${us_rev:,.0f} | US Commission: ${us_comm:,.0f}")

    smart_promo: list[dict] = []
    if SMART_PROMO_FILE.exists():
        smart_promo = json.loads(SMART_PROMO_FILE.read_text(encoding="utf-8-sig"))
        print(f"  Smart promo: {len(smart_promo)} monthly entries loaded")
    else:
        print("  Smart promo: no data/smart_promo_monthly.json found -- using empty")

    return aff_daily, orders_daily, smart_promo


if __name__ == "__main__":
    aff, orders, sp = run()
    print(f"\nAff daily rows: {len(aff)}")
    if aff:
        print("Sample aff:", aff[0])
    print(f"Orders daily rows: {len(orders)}")
    print(f"Smart promo entries: {len(sp)}")
