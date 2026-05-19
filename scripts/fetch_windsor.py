"""
fetch_windsor.py — Pull TikTok Shop orders + TikTok Ads spend from Windsor.ai.

Windsor REST API:
  GET https://connectors.windsor.ai/all
    ?api_key=KEY
    &data_source=tiktok_shop|tiktok
    &fields=f1,f2,...
    &date_from=YYYY-MM-DD
    &date_to=YYYY-MM-DD
    &account_id=ACCOUNT_ID
    &_renderer=json
  Response: { "data": [...] }

Produces / updates:
  data/windsor_cache/orders_uk_YYYY-MM-DD.json
  data/windsor_cache/orders_us_YYYY-MM-DD.json
  data/windsor_cache/ads_uk_YYYY-MM-DD.json
  data/windsor_cache/ads_us_YYYY-MM-DD.json
  data/windsor_orders.json  <- aggregated order rows (orders_daily shape)
  data/windsor_ads.json     <- ad spend data (ad_spend_daily + ad_spend_30d shape)
"""

import json
import os
import pathlib
import time
from datetime import date, timedelta
from collections import defaultdict
import requests
from dotenv import load_dotenv

ROOT = pathlib.Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

WINDSOR_BASE = os.getenv("WINDSOR_BASE_URL", "https://connectors.windsor.ai/all")
API_KEY = os.getenv("WINDSOR_API_KEY", "")
SHOP_UK = os.getenv("TT_SHOP_DATA_SOURCE_UK", "GBLC43Q29H")
SHOP_US = os.getenv("TT_SHOP_DATA_SOURCE_US", "USLCEGEVCN")
ADS_UK = os.getenv("TT_ADS_DATA_SOURCE_UK", "7506508260422287376")
ADS_US = os.getenv("TT_ADS_DATA_SOURCE_US", "7393105007056388112")
LOOKBACK = int(os.getenv("WINDSOR_LOOKBACK_DAYS", "90"))

CACHE_DIR = ROOT / "data" / "windsor_cache"
CACHE_DIR.mkdir(parents=True, exist_ok=True)

# ── SKU nickname mapping (CLAUDE.md priority order) ────────────────────────────
def nick_from_name(product_name: str) -> str:
    """Map Windsor product_name -> Vahdam SKU nickname. Priority order is NON-NEGOTIABLE."""
    n = (product_name or "").lower()
    # 1. Free gifts first
    if "frother" in n:
        return "Frother (free gift)"
    if "butterfly pea" in n:
        return "Butterfly Pea Tea (free gift)"
    # 2. Coffee variants (MUST come before curcumin check)
    if "mushroom coffee" in n:
        return "Coffee"
    if "ashwagandha coffee" in n:
        return "Coffee"
    if ("ksm-66" in n or "ksm66" in n) and "coffee" in n:
        return "Coffee"
    if "ksm-66" in n or "ksm66" in n:
        return "Coffee"
    if "instant coffee" in n:
        return "Coffee"
    if "coffee" in n:
        return "Coffee"
    # 3. Curcumin ONLY after all coffee checks
    if "curcumin" in n or "curcuminoid" in n:
        return "Turmeric Curcumin"
    # 4. Ashwagandha Caps (must have capsule indicator)
    if "ashwagandha" in n and ("capsule" in n or "cap" in n or "caps" in n):
        return "Ashwagandha Caps"
    if "ashwagandha" in n:
        return "Ashwagandha Caps"
    # 5. Remaining SKUs
    if "green burner" in n:
        return "Green Burner"
    if "shatavari" in n:
        return "Shatavari"
    if "turmeric ginger" in n or "ginger tea" in n:
        return "Turmeric Ginger Tea"
    if "moringa" in n:
        return "Moringa"
    if "turmeric" in n:
        return "Turmeric Curcumin"
    # Fallback
    return product_name or "Unknown"


def nick_from_sku_name(sku_name: str) -> str:
    """Map variation string -> canonical variation name."""
    s = (sku_name or "").lower()
    if "1 +" in s or "frother" in s or "starter kit" in s or "starter" in s:
        return "1 + Fr + Kit"
    if "pack of 5" in s or "5 pack" in s:
        return "Pack of 5"
    if "pack of 3" in s or "3 pack" in s:
        return "Pack of 3"
    if "pack of 2" in s or "2 pack" in s:
        return "Pack of 2"
    if "pack of 1" in s or "1 pack" in s or "single" in s:
        return "Pack of 1"
    # Fallback: return first plausible pack
    return "Pack of 1"


def nick_from_campaign(campaign: str) -> str | None:
    """Map TikTok campaign name -> SKU nickname for ad spend attribution."""
    c = (campaign or "").lower()
    # Order matters: coffee checks first
    if "ashwagandha coffee" in c or "mushroom coffee" in c or "ksm" in c:
        return "Coffee"
    if "coffee" in c or "moos" in c or "mof" in c:
        return "Coffee"
    if ("curcumin" in c or "curcuminoid" in c or "turmeric_capsule" in c
            or "turmericcapsule" in c or "tumeric_capsule" in c or "tumericcapsule" in c):
        return "Turmeric Curcumin"
    if ("turmeric" in c or "tumeric" in c) and "ginger" in c:
        return "Turmeric Ginger Tea"
    if "turmeric" in c or "tumeric" in c:
        return "Turmeric Curcumin"
    if "ashwagandha" in c:
        return "Ashwagandha Caps"
    if "green_burner" in c or "green burner" in c or "greenburner" in c:
        return "Green Burner"
    if "shatavari" in c:
        return "Shatavari"
    if "moringa" in c:
        return "Moringa"
    return None  # unallocated


# ── Windsor HTTP client ────────────────────────────────────────────────────────
def windsor_fetch(data_source: str, fields: list[str], account_id: str | None,
                  date_from: str, date_to: str) -> list[dict]:
    """Fetch Windsor.ai data with retry-on-429/5xx. Returns list of row dicts."""
    params = {
        "api_key": API_KEY,
        "data_source": data_source,
        "fields": ",".join(fields),
        "date_from": date_from,
        "date_to": date_to,
        "_renderer": "json",
    }
    if account_id:
        params["account_id"] = account_id
    for attempt in range(4):
        try:
            resp = requests.get(WINDSOR_BASE, params=params, timeout=120)
            if resp.status_code == 429 or resp.status_code >= 500:
                wait = 2 ** attempt * 3
                print(f"  Windsor HTTP {resp.status_code}, retrying in {wait}s...")
                time.sleep(wait)
                continue
            resp.raise_for_status()
            return resp.json().get("data", [])
        except requests.RequestException as e:
            print(f"  Windsor error: {e}")
            if attempt < 3:
                time.sleep(2 ** attempt * 3)
    return []


# ── TikTok Shop ORDER-table fields (one row per order) ────────────────────────
SHOP_ORDER_FIELDS = [
    "account_id",
    "order_id",
    "order_create_time",           # unix timestamp (string)
    "order_status",                # AWAITING_SHIPMENT / IN_TRANSIT / DELIVERED / COMPLETED / CANCELLED
    "order_payment_currency",      # GBP / USD
    "order_payment_sub_total",     # SKU subtotal AFTER seller discount, BEFORE platform discount
    "order_payment_platform_discount",
    "order_payment_seller_discount",
    "order_payment_total_amount",  # what the buyer paid (post all discounts)
    "order_payment_original_total_product_price",  # gross before any discount
]


def fetch_shop_orders(date_from: str, date_to: str) -> list[dict]:
    """Pull tiktok_shop Order-table for both UK + US (Windsor returns all connected accounts)."""
    print(f"  Fetching TikTok Shop orders {date_from} -> {date_to}...")
    rows = windsor_fetch("tiktok_shop", SHOP_ORDER_FIELDS, None, date_from, date_to)
    cache_file = CACHE_DIR / f"shop_orders_{date_to}.json"
    cache_file.write_text(json.dumps(rows, indent=2), encoding="utf-8")
    print(f"  -> {len(rows)} shop orders (cached {cache_file.name})")
    return rows


# ── tiktok_shop STATEMENT-table fields — SKU-level affiliate commission ─────────
SHOP_STATEMENT_FIELDS = [
    "date",
    "account_id",
    "statement_transaction_fee_affiliate_ads_commission_amount",
    "statement_transaction_fee_tap_shop_ads_commission",
]


def fetch_shop_statement(date_from: str, date_to: str) -> list[dict]:
    """Pull statement-table affiliate fees from tiktok_shop. Only includes SETTLED transactions."""
    print(f"  Fetching TikTok Shop statement (affiliate fees) {date_from} -> {date_to}...")
    rows = windsor_fetch("tiktok_shop", SHOP_STATEMENT_FIELDS, None, date_from, date_to)
    cache_file = CACHE_DIR / f"shop_statement_{date_to}.json"
    cache_file.write_text(json.dumps(rows, indent=2), encoding="utf-8")
    print(f"  -> {len(rows)} statement rows (cached {cache_file.name})")
    return rows


def aggregate_statement_aff(rows: list[dict]) -> dict:
    """Per (date, region) -> total affiliate commission fee paid (abs values).

    Note: Statement rows are date-grouped by Windsor's `date` field (settlement
    date). This is intentionally NOT shifted by shop timezone — settlement is
    already a calendar-day concept, not a per-order timestamp.
    """
    acct = _shop_region_map()
    out: dict[str, dict[str, float]] = {}
    for r in rows:
        region = acct.get(str(r.get("account_id", "") or ""))
        if not region:
            continue
        d = str(r.get("date", "") or "")[:10]
        if not d:
            continue
        aff_ads = abs(float(r.get("statement_transaction_fee_affiliate_ads_commission_amount") or 0))
        tap_ads = abs(float(r.get("statement_transaction_fee_tap_shop_ads_commission") or 0))
        out.setdefault(d, {})
        out[d][region] = out[d].get(region, 0.0) + aff_ads + tap_ads
    return out


def _load_status_filter() -> tuple[set, set]:
    """Load the order-status filter from config/order_filters.json.
    Returns (net_statuses, cancelled_statuses). Falls back to safe defaults."""
    cfg_path = ROOT / "config" / "order_filters.json"
    default_net = {"COMPLETED", "DELIVERED", "AWAITING_COLLECTION", "IN_TRANSIT", "SHIPPED"}
    default_cancel = {"CANCELLED"}
    try:
        cfg = json.loads(cfg_path.read_text(encoding="utf-8-sig"))
        net = {s.upper() for s in (cfg.get("net_order_statuses") or default_net)}
        cancel = {s.upper() for s in (cfg.get("cancelled_statuses") or default_cancel)}
        return net, cancel
    except Exception:
        return default_net, default_cancel


def aggregate_shop_orders(rows: list[dict]) -> dict:
    """
    Aggregate tiktok_shop Order rows into per-(date, region) daily totals.

    Date bucketing uses SHOP-LOCAL timezone (not UTC), matching how TikTok
    Seller Center's Order Report groups orders:
      UK shop  -> Europe/London  (BST = UTC+1 May..Oct, GMT = UTC+0 Nov..Mar)
      US shop  -> America/Los_Angeles  (PDT = UTC-7 May..Oct, PST = UTC-8 Nov..Mar)

    Status filter is configurable via config/order_filters.json. Default counts
    only orders that have reached a customer-facing state:
      net = COMPLETED + DELIVERED + AWAITING_COLLECTION + IN_TRANSIT + SHIPPED
      AWAITING_SHIPMENT, PENDING, etc. are tracked as "in-flight" and excluded
      from net_orders/net_qty/net_sales.
      CANCELLED tracked in a separate cancelled bucket.

    Falls back to UTC + safe defaults if zoneinfo or config lookup fails.
    """
    from datetime import datetime as _dt, timezone as _tz
    try:
        from zoneinfo import ZoneInfo
        UK_TZ = ZoneInfo("Europe/London")
        US_TZ = ZoneInfo("America/Los_Angeles")
    except Exception:
        UK_TZ = US_TZ = _tz.utc

    net_statuses, cancelled_statuses = _load_status_filter()
    acct = _shop_region_map()
    out: dict[str, dict] = {}
    for r in rows:
        region = acct.get(str(r.get("account_id", "") or ""))
        if not region:
            continue
        ts = r.get("order_create_time")
        if ts is None or str(ts) == "":
            continue
        try:
            shop_tz = UK_TZ if region == "UK" else US_TZ
            day = _dt.fromtimestamp(int(ts), tz=shop_tz).strftime("%Y-%m-%d")
        except (ValueError, TypeError):
            continue
        status = str(r.get("order_status", "") or "").upper()
        is_cancelled = status in cancelled_statuses
        is_net = status in net_statuses  # customer-facing, count toward net_orders

        sub_total = float(r.get("order_payment_sub_total") or 0)
        plat_disc = float(r.get("order_payment_platform_discount") or 0)
        seller_disc = float(r.get("order_payment_seller_discount") or 0)
        gross = float(r.get("order_payment_original_total_product_price") or 0)
        total_paid = float(r.get("order_payment_total_amount") or 0)

        day_map = out.setdefault(day, {})
        b = day_map.setdefault(region, {
            "currency": "GBP" if region == "UK" else "USD",
            "orders": 0, "net_orders": 0, "cancelled_orders": 0, "inflight_orders": 0,
            "gross": 0.0, "plat_disc": 0.0, "seller_disc": 0.0,
            "sub_total": 0.0, "net_sales": 0.0, "total_paid": 0.0,
            "cancelled_amt": 0.0,
        })
        b["orders"] += 1
        if is_cancelled:
            b["cancelled_orders"] += 1
            b["cancelled_amt"] += total_paid
        elif is_net:
            # Customer-facing — counts toward net totals.
            b["net_orders"] += 1
            b["net_sales"] += total_paid + plat_disc  # Subtotal-after-discount + plat_disc (TT-funded)
            b["gross"] += gross
            b["plat_disc"] += plat_disc
            b["seller_disc"] += seller_disc
            b["sub_total"] += sub_total
            b["total_paid"] += total_paid
        else:
            # In-flight (AWAITING_SHIPMENT, PENDING, etc.) — excluded from net.
            b["inflight_orders"] += 1
    return out


# ── Aggregate orders -> orders_daily shape ─────────────────────────────────────
def aggregate_orders(rows: list[dict], region: str) -> list[dict]:
    """
    Aggregate Windsor order rows into the pnl_daily.json orders_daily shape.
    Key: (date, region, sku, variation)
    """
    buckets: dict[tuple, dict] = {}

    for r in rows:
        # Normalise date
        raw_date = str(r.get("date", "") or "")
        if len(raw_date) > 10:
            raw_date = raw_date[:10]

        product_name = str(r.get("product_name", "") or "")
        sku_name_raw = str(r.get("sku_name", "") or "")
        sku = nick_from_name(product_name)
        variation = nick_from_sku_name(sku_name_raw or product_name)

        is_free_gift = sku in ("Frother (free gift)", "Butterfly Pea Tea (free gift)")

        order_status = str(r.get("order_status", "") or "").upper()
        is_cancelled = order_status in ("CANCELLED", "CANCEL")

        order_amount = float(r.get("order_amount") or 0)
        is_sample = (not is_cancelled) and (order_amount == 0) and (not is_free_gift)

        qty = float(r.get("quantity") or 0)
        gross_rev = float(r.get("gross_revenue") or 0)
        seller_disc = float(r.get("seller_discount") or 0)
        plat_disc = float(r.get("platform_discount") or 0)
        net_rev = float(r.get("net_revenue") or 0)
        refund = float(r.get("refund_amount") or 0)

        # net_sku = gross after seller discount, before platform discount
        net_sku = gross_rev - seller_disc

        key = (raw_date, region, sku, variation)
        if key not in buckets:
            buckets[key] = {
                "region": region,
                "sku": sku,
                "variation": variation,
                "date": raw_date,
                "currency": "GBP" if region == "UK" else "USD",
                "is_free_gift": is_free_gift,
                # raw totals (all statuses)
                "orders": 0, "qty": 0.0,
                "gross": 0.0, "plat_disc": 0.0, "seller_disc": 0.0,
                "net_sku": 0.0, "shipping": 0.0, "tax": 0.0,
                "refund": 0.0, "return_qty": 0.0, "return_value": 0.0,
                "sales": 0.0, "revenue_after_refund": 0.0,
                # exclusion buckets
                "cancelled_orders": 0, "cancelled_qty": 0.0, "cancelled_amt": 0.0,
                "sample_orders": 0, "sample_qty": 0.0,
                # net (after excluding cancelled + samples)
                "net_orders": 0, "net_qty": 0.0,
                "net_gross": 0.0, "net_plat_disc": 0.0, "net_seller_disc": 0.0,
                "net_sku_total": 0.0, "net_shipping": 0.0,
                "net_refund": 0.0, "net_return_qty": 0.0, "net_return_value": 0.0,
                "net_sales": 0.0,
                "order_amt": 0.0,
            }

        b = buckets[key]
        b["orders"] += 1
        b["qty"] += qty
        b["gross"] += gross_rev
        b["plat_disc"] += plat_disc
        b["seller_disc"] += seller_disc
        b["net_sku"] += net_sku
        b["refund"] += refund
        b["sales"] += net_rev
        b["revenue_after_refund"] += (net_rev - refund)
        b["order_amt"] += order_amount

        if is_cancelled:
            b["cancelled_orders"] += 1
            b["cancelled_qty"] += qty
            b["cancelled_amt"] += gross_rev
        elif is_sample:
            b["sample_orders"] += 1
            b["sample_qty"] += qty
        else:
            # Net order
            b["net_orders"] += 1
            b["net_qty"] += qty
            b["net_gross"] += gross_rev
            b["net_plat_disc"] += plat_disc
            b["net_seller_disc"] += seller_disc
            b["net_sku_total"] += net_sku
            b["net_refund"] += refund
            # net_sales = net_revenue (after all discounts) excluding refunds
            # Windsor net_revenue already includes platform_discount
            b["net_sales"] += max(0, net_rev - refund)

    return list(buckets.values())


# ── TikTok Ads fields ──────────────────────────────────────────────────────────
# `spend`           = standard tiktok ads (Conversion/Reach/Sales/Traffic/etc.)
# `gmv_max_ads_spend` = TikTok Shop Ads (Product GMV Max, LIVE GMV Max, Auto)
# True total ad spend = spend + gmv_max_ads_spend
ADS_FIELDS = [
    "date",
    "account_id",
    "campaign_name",
    "spend",
    "gmv_max_ads_spend",
    "impressions",
    "clicks",
    "conversions",
]


def fetch_ads_all(date_from: str, date_to: str) -> list[dict]:
    """Fetch all TikTok Ads data (Windsor returns all accounts; filter by account_id later)."""
    print(f"  Fetching TikTok Ads spend (all accounts) {date_from} -> {date_to}...")
    rows = windsor_fetch("tiktok", ADS_FIELDS, None, date_from, date_to)
    cache_file = CACHE_DIR / f"ads_all_{date_to}.json"
    cache_file.write_text(json.dumps(rows, indent=2), encoding="utf-8")
    print(f"  -> {len(rows)} rows (cached {cache_file.name})")
    return rows


ACCOUNT_REGION = {}  # populated lazily after env vars load


def _account_region_map() -> dict[str, str]:
    """Return {account_id_str: region} for tiktok ADS accounts."""
    return {str(ADS_UK): "UK", str(ADS_US): "US"}


def _shop_region_map() -> dict[str, str]:
    """Return {account_id_str: region} for tiktok_shop accounts."""
    return {str(SHOP_UK): "UK", str(SHOP_US): "US"}


def aggregate_ads(all_rows: list[dict],
                  date_from: str, date_to: str) -> tuple[dict, dict]:
    """
    Build ad_spend_daily (full window, all ad cost) and ad_spend_30d (L30, Shop Ads only).
      - daily_by_sku / daily_region_total: full window, spend + gmv_max_ads_spend.
      - ad_spend_30d: last 30 days from date_to, gmv_max_ads_spend only (matches
        Seller Center "Marketing -> Shop ads" view).
    """
    from datetime import timedelta as _td
    acct_map = _account_region_map()
    l30_end = date.fromisoformat(date_to)
    l30_start = (l30_end - _td(days=29)).isoformat()
    l30_end_s = l30_end.isoformat()

    daily_by_sku: dict[str, dict[str, dict[str, float]]] = {"UK": {}, "US": {}}
    daily_region_total: dict[str, dict[str, float]] = {"UK": {}, "US": {}}
    l30_campaign_shopads: dict[str, dict[str, float]] = {"UK": {}, "US": {}}
    l30_region_shopads: dict[str, float] = {"UK": 0.0, "US": 0.0}

    unknown_accounts: set[str] = set()
    for r in all_rows:
        acct_id = str(r.get("account_id", "") or "")
        region = acct_map.get(acct_id)
        if not region:
            unknown_accounts.add(acct_id)
            continue
        raw_date = str(r.get("date", "") or "")
        if len(raw_date) > 10:
            raw_date = raw_date[:10]
        campaign = str(r.get("campaign_name", "") or "")
        std_spend = float(r.get("spend") or 0)
        gmv_max_spend = float(r.get("gmv_max_ads_spend") or 0)
        total_spend = std_spend + gmv_max_spend
        if total_spend <= 0:
            continue

        sku = nick_from_campaign(campaign)
        sku_key = sku if sku else "(unallocated)"

        day_map = daily_by_sku[region].setdefault(raw_date, {})
        day_map[sku_key] = day_map.get(sku_key, 0.0) + total_spend
        daily_region_total[region][raw_date] = (
            daily_region_total[region].get(raw_date, 0.0) + total_spend
        )

        if gmv_max_spend > 0 and l30_start <= raw_date <= l30_end_s:
            l30_campaign_shopads[region][campaign] = (
                l30_campaign_shopads[region].get(campaign, 0.0) + gmv_max_spend
            )
            l30_region_shopads[region] += gmv_max_spend

    if unknown_accounts:
        print(f"  Warning: {len(unknown_accounts)} rows with unknown account_ids: {unknown_accounts}")

    product_gmv_max: dict[str, list] = {"UK": [], "US": []}
    live_gmv_max: dict[str, list] = {"UK": [], "US": []}
    for region in ("UK", "US"):
        for campaign, cost in sorted(l30_campaign_shopads[region].items(), key=lambda x: -x[1]):
            sku = nick_from_campaign(campaign)
            entry = {"campaign": campaign, "cost": round(cost, 2)}
            if sku:
                entry["sku"] = sku
            # Bucket by campaign type, not just SKU match.
            # LIVE creator streams (e.g. "Sandra_LIVE GMV Max", "Live Brand Handle"
            # for Alex) -> live_gmv_max. Everything else with Shop Ads spend
            # (Product GMV Max, Auto-created Promotions, anchor / handle GMV Max)
            # -> product_gmv_max.
            c_lower = campaign.lower()
            is_live = "_live gmv max" in c_lower or "live gmv max" in c_lower \
                      or "live brand handle" in c_lower
            if is_live:
                live_gmv_max[region].append(entry)
            else:
                product_gmv_max[region].append(entry)

    today = date.today().isoformat()
    ad_spend_daily = {
        "pulled_at": today,
        "window_start": date_from,
        "window_end": date_to,
        "source": "Windsor.ai tiktok connector (spend + gmv_max_ads_spend, full window)",
        "currency": {"UK": "GBP", "US": "USD"},
        "days": sorted(
            set(list(daily_region_total["UK"].keys()) + list(daily_region_total["US"].keys()))
        ),
        "daily_region_total": {
            "UK": daily_region_total["UK"],
            "US": daily_region_total["US"],
        },
        "daily_by_sku": daily_by_sku,
    }

    ad_spend_30d = {
        "pulled_at": today,
        "window_start": l30_start,
        "window_end": l30_end_s,
        "source": "Windsor.ai tiktok gmv_max_ads_spend (Shop Ads only, L30)",
        "UK": {
            "currency": "GBP",
            "total_cost": round(l30_region_shopads["UK"], 2),
            "product_gmv_max": product_gmv_max["UK"],
            "live_gmv_max": live_gmv_max["UK"],
        },
        "US": {
            "currency": "USD",
            "total_cost": round(l30_region_shopads["US"], 2),
            "product_gmv_max": product_gmv_max["US"],
            "live_gmv_max": live_gmv_max["US"],
        },
    }

    return ad_spend_daily, ad_spend_30d


# ── Main ───────────────────────────────────────────────────────────────────────
def run(lookback_days: int = LOOKBACK, shop_topup_days: int = 14) -> tuple[dict, dict, dict, dict]:
    """
    Pull TikTok Ads spend + TikTok Shop orders + Statement affiliate fees from Windsor.
    Returns (ad_spend_daily, ad_spend_30d, shop_orders_daily, shop_aff_daily).

    shop_orders_daily is the per-(date, region) daily totals from tiktok_shop
    Order-table. The merge step uses it to top-up orders_daily for days not
    covered by affiliate CSVs / reference baseline.

    shop_topup_days controls how many days back to pull tiktok_shop (default 14;
    enough to overlap the reference baseline tail and cover any CSV lag).
    """
    if not API_KEY:
        raise RuntimeError("WINDSOR_API_KEY not set in .env")

    today = date.today()
    date_from = (today - timedelta(days=lookback_days)).isoformat()
    date_to = today.isoformat()

    print(f"\n=== Windsor fetch (ads + Shop Ads GMV Max): {date_from} -> {date_to} ===")

    # Ads (UK + US combined response, split by account_id)
    all_ads = fetch_ads_all(date_from, date_to)
    ad_spend_daily, ad_spend_30d = aggregate_ads(all_ads, date_from, date_to)
    (ROOT / "data" / "windsor_ads_daily.json").write_text(
        json.dumps(ad_spend_daily, indent=2), encoding="utf-8"
    )
    (ROOT / "data" / "windsor_ads_30d.json").write_text(
        json.dumps(ad_spend_30d, indent=2), encoding="utf-8"
    )
    print(f"Windsor: UK ad spend £{ad_spend_30d['UK']['total_cost']:,.0f}, "
          f"US ad spend ${ad_spend_30d['US']['total_cost']:,.0f}")

    # TikTok Shop orders (last N days). We pull date_to + 1 day in UTC because
    # Windsor's date filter is UTC-based, but we bucket results by SHOP-LOCAL
    # timezone (Europe/London for UK, America/Los_Angeles for US) — without the
    # +1 buffer we'd miss US orders placed late-evening PDT that Windsor stamps
    # to the next UTC calendar day.
    shop_from = (today - timedelta(days=shop_topup_days)).isoformat()
    shop_to = (today + timedelta(days=1)).isoformat()
    print(f"\n=== Windsor TikTok Shop orders: {shop_from} -> {shop_to} (shop-local TZ bucketed) ===")
    shop_rows = fetch_shop_orders(shop_from, shop_to)
    shop_orders_daily = aggregate_shop_orders(shop_rows)
    (ROOT / "data" / "windsor_shop_orders_daily.json").write_text(
        json.dumps(shop_orders_daily, indent=2), encoding="utf-8"
    )
    # Print a summary of the last 5 days
    days = sorted(shop_orders_daily.keys())[-5:]
    for d in days:
        regions = shop_orders_daily[d]
        uk = regions.get("UK", {})
        us = regions.get("US", {})
        print(f"  {d}: UK net_orders={uk.get('net_orders',0)} net_sales=£{uk.get('net_sales',0):,.0f}"
              f" | US net_orders={us.get('net_orders',0)} net_sales=${us.get('net_sales',0):,.0f}")

    # Health check: detect Windsor UK outage and log it explicitly so downstream
    # knows to use the manual CSV fallback (raw_csvs/All order-UK-*.csv) instead
    # of treating 0 as actual data.
    uk_total = sum((rs.get("UK", {}).get("orders", 0) or 0) for rs in shop_orders_daily.values())
    us_total = sum((rs.get("US", {}).get("orders", 0) or 0) for rs in shop_orders_daily.values())
    if uk_total == 0 and us_total > 0:
        outage_msg = (
            f"WINDSOR_UK_DISCONNECTED — 0 UK rows returned for window {shop_from} -> {shop_to}, "
            f"but {us_total} US rows received. Reconnect tiktok_shop UK account "
            f"({SHOP_UK}) at windsor.ai/connectors. Pipeline will look for manual CSV "
            f"fallback in raw_csvs/All\\ order-UK-*.csv."
        )
        print(outage_msg)
        try:
            (ROOT / "logs").mkdir(exist_ok=True)
            with (ROOT / "logs" / "windsor_health.log").open("a", encoding="utf-8") as fh:
                from datetime import datetime as _dtnow
                fh.write(f"[{_dtnow.now().isoformat()}] {outage_msg}\n")
        except Exception:
            pass

    # Statement-table affiliate commission (settled transactions only)
    print(f"\n=== Windsor TikTok Shop statement (affiliate fees) {shop_from} -> {shop_to} ===")
    stmt_rows = fetch_shop_statement(shop_from, shop_to)
    shop_aff_daily = aggregate_statement_aff(stmt_rows)
    (ROOT / "data" / "windsor_shop_aff_daily.json").write_text(
        json.dumps(shop_aff_daily, indent=2), encoding="utf-8"
    )
    aff_uk = sum(d.get("UK", 0) for d in shop_aff_daily.values())
    aff_us = sum(d.get("US", 0) for d in shop_aff_daily.values())
    print(f"  Statement affiliate fees (top-up window): UK £{aff_uk:,.0f} | US ${aff_us:,.0f}")

    return ad_spend_daily, ad_spend_30d, shop_orders_daily, shop_aff_daily


if __name__ == "__main__":
    run()
