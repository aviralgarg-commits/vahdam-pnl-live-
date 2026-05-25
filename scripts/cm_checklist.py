"""12-point P&L checklist — UK and US, L30 ending 2026-05-24.

Mirrors the JS in build_dashboard.py exactly. Writes a markdown report.
"""
from __future__ import annotations
import json
from datetime import date, timedelta
from pathlib import Path
import sys

LIVE = Path(__file__).resolve().parent.parent
LABEL = sys.argv[1] if len(sys.argv) > 1 else 'FIRST'

d = json.load(open(LIVE / 'data' / 'pnl_daily.json'))
END = date(2026, 5, 24)
DAYS = {(END - timedelta(days=i)).isoformat() for i in range(30)}
WSTART = min(DAYS); WEND = max(DAYS)

tax = (d.get('costs_uk') or {}).get('uk_tax_rules', {})
VAT_KEPT = set(tax.get('vat_kept_skus', ['Turmeric Ginger Tea']))
VAT_REMOVED_ALWAYS = set(tax.get('vat_removed_always',
                                  ['Green Burner', 'Ashwagandha Caps', 'Turmeric Curcumin']))
COFFEE_CUTOFF = (tax.get('vat_removed_from_date') or {}).get('Coffee', '2026-04-01')
SHIP_FROM = tax.get('shipping_per_order_from_date', '2026-03-01')
SHIP_AMT = tax.get('shipping_per_order_amount', 1.99)

UK_CPP = (d.get('costs_uk') or {}).get('costs_per_pack', {})
US_CPP = (d.get('costs_us') or {}).get('costs_per_pack', {})


def compute(region: str) -> dict:
    rows = [r for r in d['orders_daily']
            if r['region'] == region and r['date'] in DAYS and not r.get('is_free_gift')]
    net_sales = sum(r.get('net_sales', 0) for r in rows)

    vat_in_sales = 0.0
    if region == 'UK':
        for r in rows:
            sku = r['sku']
            is_zr = False
            if sku == 'Coffee':
                is_zr = (r['date'] >= COFFEE_CUTOFF)
            elif sku in VAT_REMOVED_ALWAYS:
                is_zr = True
            if is_zr:
                vat_in_sales += r.get('net_sales', 0) * (20 / 120)
    net_sales_ex_vat = net_sales - vat_in_sales

    cb = {k: 0.0 for k in ('cogs', 'commission', 'dsf', 'storage', 'vat',
                            'logistics_duty', 'logistics_cost', 'fulfillment',
                            'shipping', 'per_order_shipping')}
    cpp = UK_CPP if region == 'UK' else US_CPP
    for r in rows:
        cps = cpp.get(r['sku'])
        cp = cps.get(r['variation']) if cps else None
        q = r.get('net_qty', 0)
        o = r.get('net_orders', 0)
        sku = r['sku']
        if region == 'UK':
            if sku in VAT_KEPT:
                vat_applies = True
            elif sku == 'Coffee':
                vat_applies = (r['date'] < COFFEE_CUTOFF)
            elif sku in VAT_REMOVED_ALWAYS:
                vat_applies = False
            else:
                vat_applies = True
        else:
            vat_applies = True
        if cp:
            cb['cogs'] += (cp.get('cogs', 0) or 0) * q
            cb['commission'] += (cp.get('commission', 0) or 0) * q
            cb['dsf'] += (cp.get('digital_service_fee', 0) or 0) * q
            cb['storage'] += (cp.get('storage', 0) or 0) * q
            if vat_applies:
                cb['vat'] += (cp.get('vat', 0) or 0) * q
            cb['logistics_duty'] += (cp.get('logistics_duty', 0) or 0) * q
            cb['logistics_cost'] += (cp.get('logistics_cost', 0) or 0) * q
            cb['fulfillment'] += (cp.get('fulfillment', 0) or 0) * q
            cb['shipping'] += (cp.get('shipping', 0) or 0) * q
        if region == 'UK' and r['date'] >= SHIP_FROM:
            cb['per_order_shipping'] += o * SHIP_AMT
    total_unit_costs = sum(cb.values())
    cm1 = net_sales_ex_vat - total_unit_costs

    aff_comm = sum(r.get('aff_commission', 0) for r in d['aff_daily']
                   if r['region'] == region and r['date'] in DAYS)

    ads_map = d['ad_spend_daily']['daily_by_sku'].get(region, {})
    ad_ex = 0.0
    for day in DAYS:
        for _, v in ads_map.get(day, {}).items():
            ad_ex += v
    ad_inc = ad_ex * 1.20 if region == 'UK' else ad_ex

    sp_cost = 0.0
    for b in d.get('smart_promo_monthly', []):
        if b['region'] != region:
            continue
        ws, we = b['window_start'], b['window_end']
        tot_rev = sum(r.get('net_sales', 0) for r in d['orders_daily']
                      if r['region'] == region and ws <= r['date'] <= we)
        if tot_rev <= 0:
            continue
        f_rev = sum(r.get('net_sales', 0) for r in rows if ws <= r['date'] <= we)
        sp_cost += b['cost'] * (f_rev / tot_rev)
    sp_inc = sp_cost * 1.20 if region == 'UK' else sp_cost
    vat_rec = (ad_inc + sp_inc) * (20 / 120) if region == 'UK' else 0.0

    fs_cost = 0.0
    if region == 'UK':
        fs = (d.get('costs_uk') or {}).get('uk_free_sample_costs', {})
        per_pack = fs.get('per_pack', {})
        sd_from = fs.get('shipping_deduction_from_date', '2026-02-14')
        sd_amt = fs.get('shipping_deduction_amount', 2.0)
        for r in rows:
            sq = r.get('sample_qty', 0)
            if sq <= 0:
                continue
            pp = (per_pack.get(r['sku']) or {}).get(r['variation'], 0) or 0
            eff = max(0, pp - sd_amt) if r['date'] >= sd_from else pp
            fs_cost += sq * eff
    else:
        fs = (d.get('costs_us') or {}).get('us_free_sample_costs', {})
        per_pack = fs.get('per_pack', {})
        for r in rows:
            sq = r.get('sample_qty', 0)
            if sq <= 0:
                continue
            pp = (per_pack.get(r['sku']) or {}).get(r['variation'], 0) or 0
            fs_cost += sq * pp

    cm2 = cm1 - aff_comm - ad_inc - sp_inc + vat_rec - fs_cost
    cm2_pct = cm2 / net_sales * 100 if net_sales else 0
    return {
        'region': region, 'window': f'{WSTART} → {WEND}',
        '1_net_sales': net_sales,
        '2_vat_in_sales': vat_in_sales,
        '3_net_sales_ex_vat': net_sales_ex_vat,
        '4_total_unit_costs': total_unit_costs,
        '5_cm1': cm1,
        '6_affiliate': aff_comm,
        '7_ad_spend_inc': ad_inc,
        '8_smart_promo_inc': sp_inc,
        '9_vat_recovery': vat_rec,
        '10_free_sample_cost': fs_cost,
        '11_cm2': cm2,
        '12_cm2_pct': cm2_pct,
        '_cost_breakdown': cb,
    }


uk = compute('UK')
us = compute('US')
SYM = {'UK': '£', 'US': '$'}

ITEMS = [
    ('1', 'Net Sales (sum net_sales)', '1_net_sales'),
    ('2', 'VAT in Sales (UK supplements only; ZERO for US)', '2_vat_in_sales'),
    ('3', 'Net Sales ex-VAT', '3_net_sales_ex_vat'),
    ('4', 'Total Unit Costs (COGs + comm + DSF + storage + logistics + fulfillment + shipping + UK ship)', '4_total_unit_costs'),
    ('5', 'CM1 = (3) - (4)', '5_cm1'),
    ('6', 'Affiliate (Std + Shop Ads + Co-funded; eligible only)', '6_affiliate'),
    ('7', 'Ad Spend inc-VAT (UK x1.20)', '7_ad_spend_inc'),
    ('8', 'Smart Promo inc-VAT (UK x1.20)', '8_smart_promo_inc'),
    ('9', 'VAT Recovery (UK only)', '9_vat_recovery'),
    ('10', 'Free Sample Cost', '10_free_sample_cost'),
    ('11', 'CM2 = (5) - (6) - (7) - (8) + (9) - (10)', '11_cm2'),
    ('12', 'CM2 % of Net Sales', '12_cm2_pct'),
]

for r in (uk, us):
    print(f'\n== {r["region"]} L30 ({r["window"]}) ==')
    for num, lab, k in ITEMS:
        v = r[k]
        if 'pct' in k:
            print(f'  {num:>2}. {lab:60s} {v:>10.2f}%')
        else:
            print(f'  {num:>2}. {lab:60s} {SYM[r["region"]]}{v:>14,.2f}')
    print(' cost breakdown:', {k: round(v, 2) for k, v in r['_cost_breakdown'].items()})

# Markdown report
out = LIVE / 'logs' / f'cm_check_{LABEL}.md'
with out.open('w', encoding='utf-8') as f:
    f.write(f'# 12-point P&L checklist - {LABEL}\n\n')
    f.write(f'Generated: 2026-05-25  \nWindow: L30 ({WSTART} -> {WEND})\n\n')
    for r in (uk, us):
        f.write(f'## {r["region"]} L30\n\n')
        f.write('| # | Line | Value |\n|---|------|------:|\n')
        for num, lab, k in ITEMS:
            v = r[k]
            if 'pct' in k:
                f.write(f'| {num} | {lab} | {v:.2f}% |\n')
            else:
                f.write(f'| {num} | {lab} | {SYM[r["region"]]}{v:,.2f} |\n')
        f.write('\nCost breakdown:\n\n```\n')
        f.write(json.dumps({k: round(v, 2) for k, v in r['_cost_breakdown'].items()}, indent=2))
        f.write('\n```\n\n')
    f.write('## Sign checks\n\n')
    f.write(f'- UK CM1 positive: {"OK" if uk["5_cm1"] > 0 else "FAIL"} ({SYM["UK"]}{uk["5_cm1"]:,.2f})\n')
    f.write(f'- US CM1 positive: {"OK" if us["5_cm1"] > 0 else "FAIL"} ({SYM["US"]}{us["5_cm1"]:,.2f})\n')
    f.write(f'- UK CM2 positive: {"OK" if uk["11_cm2"] > 0 else "FAIL"} ({SYM["UK"]}{uk["11_cm2"]:,.2f})\n')
    f.write(f'- US CM2 positive: {"OK" if us["11_cm2"] > 0 else "FAIL"} ({SYM["US"]}{us["11_cm2"]:,.2f})\n')
print(f'\nWrote {out}')
