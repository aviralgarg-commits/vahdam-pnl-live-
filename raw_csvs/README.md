# Affiliate CSV drop folder

Drop new `affiliate_orders_*.csv` files exported from TikTok Seller Center → Affiliate → Orders here.

Then run:
```
python scripts/aggregate_affiliate.py
```

This will re-aggregate commissions (Std + Shop Ads + Co-funded, eligible only) and update `data/pnl_daily.json`.

Then rebuild the HTML:
```
python scripts/build_dashboard.py
```
