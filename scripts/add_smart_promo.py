"""
add_smart_promo.py — quick helper to append a Smart Promotion bucket without
touching JSON by hand. Use this whenever the Playwright scraper can't reach
Seller Center (UK auth currently broken).

Usage examples:
  python scripts/add_smart_promo.py --region UK --from 2026-05-14 --to 2026-05-19 --cost 320.50
  python scripts/add_smart_promo.py --region US --from 2026-05-12 --to 2026-05-19 --cost 2099.36 --roi 7.5

How to find the value:
  1. Open https://seller-uk.tiktok.com/promotion/program-center/smart-program/manage
     (or seller-us.tiktok.com)
  2. Click "View details" on the Smart Promotion row
  3. Set the date picker to cover the gap (typically yesterday's bucket's end +1
     through today)
  4. Read "Seller promotion cost" — that's the --cost value

Appends to data/smart_promo_monthly.json. Never overwrites adjacent buckets.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys
from datetime import datetime, date as _date

ROOT = pathlib.Path(__file__).resolve().parent.parent
PATH = ROOT / "data" / "smart_promo_monthly.json"


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--region", required=True, choices=["UK", "US"])
    p.add_argument("--from", dest="window_start", required=True, help="YYYY-MM-DD")
    p.add_argument("--to",   dest="window_end",   required=True, help="YYYY-MM-DD")
    p.add_argument("--cost", required=True, type=float, help="Seller promotion cost")
    p.add_argument("--gmv", type=float, default=0.0, help="Smart Promotion GMV (optional)")
    p.add_argument("--orders", type=int, default=0, help="Orders via Smart Promo (optional)")
    p.add_argument("--new-customers", type=int, default=0, help="(optional)")
    p.add_argument("--roi", type=float, default=0.0, help="(optional)")
    p.add_argument("--fee-rate", type=float, default=None, help="US only, e.g. 0.0349")
    args = p.parse_args()

    # Validate date
    try:
        _date.fromisoformat(args.window_start)
        _date.fromisoformat(args.window_end)
    except ValueError as e:
        print(f"ERROR: invalid date format ({e})")
        return 1
    if args.window_end < args.window_start:
        print("ERROR: --to must be >= --from"); return 1

    bucket = {
        "region": args.region,
        "month": args.window_start[:7],
        "window_start": args.window_start,
        "window_end": args.window_end,
        "cost": round(args.cost, 2),
        "currency": "GBP" if args.region == "UK" else "USD",
        "smart_promo_gmv": args.gmv,
        "orders_via_smart_promo": args.orders,
        "new_customers": args.new_customers,
        "roi": args.roi,
        "source": f"TikTok {args.region} Seller Center > Marketing > Smart Promotion (manual entry)",
        "pulled_at": _date.today().isoformat(),
    }
    if args.fee_rate is not None:
        bucket["seller_fee_rate"] = args.fee_rate

    data = []
    if PATH.exists():
        data = json.loads(PATH.read_text(encoding="utf-8-sig"))
    # Dedup: replace existing bucket with same (region, window_start, window_end)
    key = (args.region, args.window_start, args.window_end)
    before = len(data)
    data = [b for b in data if (b.get("region"), b.get("window_start"), b.get("window_end")) != key]
    replaced = before > len(data)
    data.append(bucket)
    PATH.write_text(json.dumps(data, indent=2), encoding="utf-8")
    verb = "REPLACED" if replaced else "APPENDED"
    print(f"{verb} bucket: {args.region} {args.window_start} -> {args.window_end}  "
          f"cost={bucket['currency']} {args.cost}")
    print(f"Total buckets in file: {len(data)}")
    print(f"Run scripts/refresh_daily.py to rebuild the dashboard with this value.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
