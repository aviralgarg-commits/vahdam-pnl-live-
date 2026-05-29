"""
Re-aggregate affiliate commissions properly:
- Date parse: DD/MM/YYYY → YYYY-MM-DD
- Commission = Standard + Shop Ads + Co-funded creator bonus
- For each component: use Actual if > 0 else Estimated
- Exclude Order Status = 'Ineligible'
- Keep Settled + Pending
- DEDUP: (Order ID, Product ID) — TikTok ships the same line-item across
  multiple page-exports and across overlapping date-range exports. Without
  dedup the L30 affiliate triple-counts (was ~3x the actual). Largest CSV
  processed first so subsequent files only add genuinely new line-items.
Aggregate by (date, region, sku) for the daily series.
"""
import csv, glob, json, os, re
from collections import defaultdict

import pathlib
ROOT = pathlib.Path(__file__).resolve().parent.parent
DOWNLOADS = str(ROOT / 'raw_csvs')
OUT = str(ROOT / 'data' / 'pnl_daily.json')

# SKU nickname mapping (copied from existing logic)
NICK = {
  '1729697274006116523': 'Turmeric Curcumin',     # Turmeric Curcumin 1800mg (UK)
  '1729697263975372971': 'Ashwagandha Caps',      # Ashwagandha L-Theanine
  '1729697281939642539': 'Green Burner',          # Green Burner
  '1729509299352344747': 'Coffee',                # KSM-66 Ashwagandha Coffee
  '1729629514098776235': 'Turmeric Ginger Tea',   # Turmeric Ginger Tea
}

# Function: derive SKU nickname from product name (fallback)
def nick_from_name(name):
    n = (name or '').lower()
    if 'frother' in n: return 'Frother'
    if 'mushroom coffee' in n: return 'Coffee'
    if 'ashwagandha coffee' in n: return 'Coffee'
    if 'ksm-66' in n and 'coffee' in n: return 'Coffee'
    if 'instant coffee' in n: return 'Coffee'
    if 'curcumin' in n or 'curcuminoids' in n: return 'Turmeric Curcumin'
    if 'ashwagandha' in n and 'capsule' in n: return 'Ashwagandha Caps'
    if 'ashwagandha' in n and ('cap' in n or 'veg' in n or 'pill' in n): return 'Ashwagandha Caps'
    if 'green burner' in n: return 'Green Burner'
    if 'shatavari' in n: return 'Shatavari'
    if 'turmeric ginger' in n and 'tea' in n: return 'Turmeric Ginger Tea'
    if 'moringa' in n: return 'Moringa'
    if 'butterfly pea' in n: return 'Butterfly Pea'
    return 'Other'

def f(x):
    try: return float(str(x).strip().replace(',', ''))
    except: return 0.0

def parse_date(s):
    s = (s or '').strip()
    if len(s) >= 10 and '/' in s:
        try:
            d, m, y = s[:10].split('/')
            return f'{y}-{m.zfill(2)}-{d.zfill(2)}'
        except:
            return ''
    return s[:10] if s else ''

# (date, region, sku) -> aggregates
buckets = defaultdict(lambda: {'aff_orders':0, 'aff_revenue':0.0, 'aff_commission':0.0,
                                'aff_std':0.0, 'aff_shop_ads':0.0, 'aff_co_funded':0.0})

stats = {'total_rows':0, 'ineligible':0, 'invalid_date':0, 'unknown_region':0,
         'in_window':0, 'dupe_skipped':0}

# DEDUP: (Order ID, Product ID) — TikTok exports overlap across pages/date
# ranges, so a row can appear in 2-3 CSVs. Without dedup the L30 sum bloats ~3x.
# Process the LARGEST CSV first (assumed authoritative / most recent); smaller
# files then only contribute genuinely new line-items.
seen_line_items = set()

files = sorted(glob.glob(os.path.join(DOWNLOADS, 'affiliate_orders_*.csv')),
               key=lambda fp: os.path.getsize(fp), reverse=True)
print(f'Files: {len(files)} (largest first)')

for fp in files:
    with open(fp, encoding='utf-8', errors='replace') as fh:
        rdr = csv.reader(fh)
        try:
            headers = next(rdr)
        except StopIteration:
            continue
        if len(headers) < 28:
            continue
        # Detect column layout — UK CSVs have 31 columns (with "Creator Region"), US CSVs have 30 (without).
        # Offset: 0 for UK (31-col), -1 for US (30-col) for columns after 'Content Type'.
        has_creator_region = 'Creator Region' in headers
        off = 0 if has_creator_region else -1
        IDX_TIME_CREATED = 26 + off
        IDX_STD_EST = 18 + off
        IDX_STD_ACT = 20 + off
        IDX_SA_EST = 22 + off
        IDX_SA_ACT = 23 + off
        IDX_CF_EST = 24 + off
        IDX_CF_ACT = 25 + off
        for row in rdr:
            stats['total_rows'] += 1
            if len(row) < 28 + off: continue
            status = row[10] if len(row) > 10 else ''
            if status == 'Ineligible':
                stats['ineligible'] += 1
                continue
            # DEDUP key: (Order ID, Product ID). Skip if we've already counted
            # this exact line-item from a prior (larger) CSV.
            order_id = row[0] if len(row) > 0 else ''
            product_id = row[1] if len(row) > 1 else ''
            key_li = (order_id, product_id)
            if key_li in seen_line_items:
                stats['dupe_skipped'] += 1
                continue
            seen_line_items.add(key_li)
            tc = parse_date(row[IDX_TIME_CREATED])
            if not tc or len(tc) != 10:
                stats['invalid_date'] += 1
                continue
            currency = row[6] if len(row) > 6 else ''
            region = 'UK' if currency == 'GBP' else ('US' if currency == 'USD' else None)
            if not region:
                stats['unknown_region'] += 1
                continue
            product_name = row[2] if len(row) > 2 else ''
            sku_nick = NICK.get(product_id) or nick_from_name(product_name)
            payment = f(row[5])
            qty = int(f(row[7])) if row[7] else 1
            std_est = f(row[IDX_STD_EST]); std_act = f(row[IDX_STD_ACT])
            sa_est = f(row[IDX_SA_EST]); sa_act = f(row[IDX_SA_ACT])
            cf_est = f(row[IDX_CF_EST]); cf_act = f(row[IDX_CF_ACT])
            std = std_act if std_act > 0 else std_est
            sa = sa_act if sa_act > 0 else sa_est
            cf = cf_act if cf_act > 0 else cf_est
            total_comm = std + sa + cf
            
            key = (tc, region, sku_nick)
            b = buckets[key]
            b['aff_orders'] += 1  # each row is one order line
            b['aff_revenue'] += payment
            b['aff_commission'] += total_comm
            b['aff_std'] += std
            b['aff_shop_ads'] += sa
            b['aff_co_funded'] += cf
            stats['in_window'] += 1

print('Stats:', stats)
print(f'Buckets: {len(buckets)}')

# Build aff_daily list
aff_daily = []
for (date, region, sku), b in sorted(buckets.items()):
    aff_daily.append({
        'date': date, 'region': region, 'sku': sku,
        'aff_orders': b['aff_orders'],
        'aff_revenue': round(b['aff_revenue'], 2),
        'aff_commission': round(b['aff_commission'], 2),
        'aff_std': round(b['aff_std'], 2),
        'aff_shop_ads': round(b['aff_shop_ads'], 2),
        'aff_co_funded': round(b['aff_co_funded'], 2),
    })

# Summarize L30
WIN_S = '2026-04-14'
WIN_E = '2026-05-13'
uk_l30 = us_l30 = 0
for r in aff_daily:
    if r['date'] < WIN_S or r['date'] > WIN_E: continue
    if r['region'] == 'UK': uk_l30 += r['aff_commission']
    elif r['region'] == 'US': us_l30 += r['aff_commission']
print(f'UK L30 aff commission: £{uk_l30:,.2f}')
print(f'US L30 aff commission: ${us_l30:,.2f}')

# Update pnl_daily.json
d = json.load(open(OUT))
d['aff_daily'] = aff_daily
notes = [n for n in d.get('notes', []) if 'Affiliate' not in n]
notes.append('Affiliate commission = Standard + Shop Ads + Co-funded creator bonus. Actual where >0, else Estimated. Order Status = Ineligible excluded. Date parsed from DD/MM/YYYY (Time Created).')
d['notes'] = notes
json.dump(d, open(OUT, 'w'), separators=(',', ':'))
print('pnl_daily.json updated')
