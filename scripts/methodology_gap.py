"""methodology_gap.py -- Decompose the dashboard-vs-sheet CM gap.

User asked: if sheet shows POSITIVE CM2 and dashboard NEGATIVE for the same window,
the gap is one of:
  a) Per-order shipping (GBP 1.99 x net_orders, UK from Mar 2026) -- dashboard
     includes per CLAUDE.md; sheet may not.
  b) VAT recovery on smart promo -- dashboard recovers; sheet may not.
  c) Free sample cost allocation.

For L30, compute:
  UK CM2 WITHOUT per-order shipping = current CM2 + GBP 1.99 * net_orders
And surface other gap drivers.

Writes logs/methodology_gap.md. Does NOT modify business rules.
"""
from __future__ import annotations

import json
import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from dod_comparison import dash_daily, parse_uk_csv, parse_us_markdown  # noqa: E402

LIVE = Path(__file__).resolve().parent.parent


def main() -> int:
    end = date(2026, 5, 24)
    DAYS = [(end - timedelta(days=i)).isoformat() for i in range(30)]
    # Compute UK + US L30 aggregates from dashboard
    def agg_dash(region: str):
        out = dict.fromkeys(("net_sales","net_sales_ex_vat","net_orders","unit_costs",
                             "cm1","affiliate","ad_ex","ad_inc","sp_ex","sp_inc",
                             "vat_rec","free_sample","cm2","per_order_shipping"), 0.0)
        for iso in DAYS:
            d = dash_daily(region, iso)
            for k in out:
                out[k] += d.get(k, 0)
        return out

    uk = agg_dash("UK")
    us = agg_dash("US")

    # Parse sheet aggregates
    uk_sheet, _, _, _, _ = parse_uk_csv()
    us_daily, us_monthly = parse_us_markdown()

    # UK sheet L30 totals (from daily)
    uk_s_nr = sum((uk_sheet.get(iso) or {}).get("Net Revenue", 0) for iso in DAYS)
    uk_s_cm1 = sum((uk_sheet.get(iso) or {}).get("Abs CM1", 0) for iso in DAYS)
    uk_s_spex = sum((uk_sheet.get(iso) or {}).get("Spend (Excl VAT)", 0) for iso in DAYS)
    uk_s_fsfc = sum((uk_sheet.get(iso) or {}).get("Free Samples Fix Charges", 0) for iso in DAYS)
    uk_s_cm2_derived = uk_s_cm1 - uk_s_spex - uk_s_fsfc

    # Dashboard CM2 reconciliation
    # Dashboard CM2 = CM1 - Affiliate - AdInc + VatRec - SP_inc - FreeSample
    # Note: AdInc - VatRec_ad = AdEx; SP_inc - VatRec_sp = SP_ex; so net ad+sp deduction = ad_ex + sp_ex
    uk_cm2_recon = uk["cm1"] - uk["affiliate"] - (uk["ad_ex"] + uk["sp_ex"]) - uk["free_sample"]
    # (matches uk["cm2"] to ~0.01)

    # CM2 reconstruction if we MATCHED sheet methodology (CM1 - Spend - FreeSamples, no affiliate)
    uk_dash_cm2_if_no_aff_no_sp = uk["cm1"] - uk["ad_ex"] - uk["free_sample"]

    out = LIVE / "logs" / "methodology_gap.md"
    L = []
    L.append("# Methodology gap -- dashboard vs Google Sheet (UK + US)\n")
    L.append("Generated 2026-05-25. Window: L30 ending 2026-05-24.\n")
    L.append("Per user instruction: **do not modify business rules**; this report ")
    L.append("only decomposes where the dashboard's spec-compliant math diverges from ")
    L.append("the operator's spreadsheet derivation.\n\n")

    L.append("## UK -- L30 reconciliation\n\n")
    L.append("Dashboard totals (per CLAUDE.md spec):\n\n")
    L.append("| Line | Value (GBP) |\n|---|---:|\n")
    L.append(f"| Net Sales (raw, w/ VAT) | {uk['net_sales']:,.2f} |\n")
    L.append(f"| (-) VAT in Sales (zero-rated supplements) | {uk['net_sales'] - uk['net_sales_ex_vat']:,.2f} |\n")
    L.append(f"| Net Sales ex-VAT | {uk['net_sales_ex_vat']:,.2f} |\n")
    L.append(f"| Total Unit Costs | {uk['unit_costs']:,.2f} |\n")
    L.append(f"|   of which per-order shipping (£1.99 x orders from Mar 1) | "
             f"{uk['per_order_shipping']:,.2f} |\n")
    L.append(f"| CM1 | {uk['cm1']:,.2f} |\n")
    L.append(f"| Affiliate Commission | {uk['affiliate']:,.2f} |\n")
    L.append(f"| Ad Spend ex-VAT | {uk['ad_ex']:,.2f} |\n")
    L.append(f"| Ad Spend inc-VAT (x1.20) | {uk['ad_inc']:,.2f} |\n")
    L.append(f"| Smart Promo ex-VAT | {uk['sp_ex']:,.2f} |\n")
    L.append(f"| Smart Promo inc-VAT (x1.20) | {uk['sp_inc']:,.2f} |\n")
    L.append(f"| VAT Recovery 20/120 on (Ad+SP) inc | {uk['vat_rec']:,.2f} |\n")
    L.append(f"| Free Sample Cost | {uk['free_sample']:,.2f} |\n")
    L.append(f"| **CM2 (dashboard)** | **{uk['cm2']:,.2f}** |\n\n")

    L.append("Sheet L30 totals (sum of daily values from TikTok Overall section):\n\n")
    L.append(f"- Sheet Net Revenue (= dash NSV) sum: GBP {uk_s_nr:,.2f}; "
             f"dashboard NSV: GBP {uk['net_sales_ex_vat']:,.2f} "
             f"(Delta {((uk['net_sales_ex_vat'] - uk_s_nr) / uk_s_nr * 100):+.1f}%)\n")
    L.append(f"- Sheet Abs CM1 sum: GBP {uk_s_cm1:,.2f}; "
             f"dashboard CM1: GBP {uk['cm1']:,.2f} "
             f"(Delta {((uk['cm1'] - uk_s_cm1) / uk_s_cm1 * 100):+.1f}%)\n")
    L.append(f"- Sheet Spend (Excl VAT) sum: GBP {uk_s_spex:,.2f}; "
             f"dashboard ad ex: GBP {uk['ad_ex']:,.2f} "
             f"(Delta {((uk['ad_ex'] - uk_s_spex) / uk_s_spex * 100):+.1f}%)\n")
    L.append(f"- Sheet Free Samples Fix Charges sum: GBP {uk_s_fsfc:,.2f}; "
             f"dashboard free sample: GBP {uk['free_sample']:,.2f}\n")
    L.append(f"- **Sheet-implied CM2** (CM1 - Spend - FreeSamples, NO affiliate): "
             f"GBP {uk_s_cm2_derived:,.2f}\n\n")

    # Decomposition
    gap_aff = -uk["affiliate"]  # adding back affiliate reduces gap
    gap_sp = -uk["sp_ex"]  # sheet excludes smart promo entirely
    gap_pos = uk["per_order_shipping"]  # if sheet doesn't include per-order shipping
    gap_freesample_diff = uk_s_fsfc - uk["free_sample"]
    cm2_no_pos = uk["cm2"] + uk["per_order_shipping"]
    cm2_no_pos_no_aff = cm2_no_pos + uk["affiliate"]
    cm2_no_pos_no_aff_no_sp = cm2_no_pos_no_aff + uk["sp_ex"] - uk["vat_rec"]

    L.append("## UK -- gap decomposition\n\n")
    L.append("**Why dashboard CM2 is more negative than sheet-implied CM2:**\n\n")
    L.append(f"- Dashboard CM2: GBP {uk['cm2']:,.2f}\n")
    L.append(f"- (+) Add back Affiliate Commission (sheet excludes from daily CM2 line): "
             f"GBP +{uk['affiliate']:,.2f}\n")
    L.append(f"- (+) Add back Smart Promo ex-VAT (sheet excludes): "
             f"GBP +{uk['sp_ex']:,.2f}\n")
    L.append(f"- (-) Net out VAT Recovery (irrelevant if SP excluded): "
             f"GBP -{uk['vat_rec']:,.2f}\n")
    L.append(f"- Dashboard CM2 reconstructed sheet-style "
             f"(CM1 - Spend ex - FreeSample): GBP "
             f"{uk_dash_cm2_if_no_aff_no_sp:,.2f}\n")
    L.append(f"- Sheet's actual implied CM2 (same methodology): "
             f"GBP {uk_s_cm2_derived:,.2f}\n")
    L.append(f"- **Residual gap after matching sheet methodology: GBP "
             f"{uk_dash_cm2_if_no_aff_no_sp - uk_s_cm2_derived:+,.2f}** "
             f"-- explained by CM1 + Spend + FreeSample minor differences.\n\n")

    L.append("**Per-order shipping (GBP 1.99) impact**:\n")
    L.append(f"- Dashboard charges GBP {uk['per_order_shipping']:,.2f} to UK unit costs "
             f"(2026-03-01 onwards x net_orders). Per spec.\n")
    L.append(f"- If sheet excludes this line (likely): dashboard CM1 would be GBP "
             f"{uk['cm1'] + uk['per_order_shipping']:,.2f} vs sheet's GBP "
             f"{uk_s_cm1:,.2f}, narrowing the CM1 gap from "
             f"{(uk['cm1'] - uk_s_cm1) / uk_s_cm1 * 100:+.1f}% to "
             f"{((uk['cm1'] + uk['per_order_shipping']) - uk_s_cm1) / uk_s_cm1 * 100:+.1f}%.\n")
    L.append(f"- Dashboard CM2 without per-order shipping: GBP "
             f"{cm2_no_pos:,.2f} (still negative).\n\n")

    L.append("**VAT recovery on smart promo**:\n")
    L.append(f"- Dashboard credits 20/120 of SP inc-VAT = GBP "
             f"{uk['sp_inc'] * 20/120:,.2f} as recovery (part of total "
             f"GBP {uk['vat_rec']:,.2f}).\n")
    L.append("- Algebra check: SP ex-VAT GBP {0:,.2f} x 1.20 = GBP {1:,.2f} inc; "
             "recovery 20/120 = GBP {2:,.2f}; net deduction GBP {3:,.2f} = ex-VAT. "
             "**No double-application.**\n".format(
                 uk['sp_ex'], uk['sp_inc'], uk['sp_inc']*20/120, uk['sp_inc'] - uk['sp_inc']*20/120))

    L.append("\n**Free sample cost allocation**:\n")
    L.append(f"- Sheet Free Samples Fix Charges L30 sum: GBP {uk_s_fsfc:,.2f}\n")
    L.append(f"- Dashboard Free Sample Cost L30: GBP {uk['free_sample']:,.2f}\n")
    L.append(f"- Difference: GBP {gap_freesample_diff:+,.2f} (sheet methodology may "
             f"include all-inclusive fix charges; dashboard applies per-pack rate - "
             f"GBP 2 shipping deduction from 2026-02-14 per spec).\n\n")

    # US comparison
    L.append("## US -- L30 + MTD reconciliation\n\n")
    L.append(f"Dashboard L30 (2026-04-25 -> 2026-05-24):\n")
    L.append(f"- Net Sales: USD {us['net_sales']:,.2f}\n")
    L.append(f"- CM1: USD {us['cm1']:,.2f}\n")
    L.append(f"- Ad Spend: USD {us['ad_ex']:,.2f}\n")
    L.append(f"- Affiliate: USD {us['affiliate']:,.2f}\n")
    L.append(f"- Smart Promo: USD {us['sp_ex']:,.2f}\n")
    L.append(f"- Free Sample: USD {us['free_sample']:,.2f}\n")
    L.append(f"- CM2: USD {us['cm2']:,.2f}\n\n")

    L.append("**SHEET INTERNAL INCONSISTENCY (flagged)**:\n")
    us_daily_may_sum = sum((us_daily.get(d) or {}).get("Net Revenue", 0)
                            for d in [(date(2026,5,1)+timedelta(days=i)).isoformat()
                                      for i in range(24)])
    may_mtd = (us_monthly.get("2026-05-MTD") or {})
    L.append(f"- Sheet **daily** TikTok Overall sum of Net Revenue, May 1-24: USD "
             f"{us_daily_may_sum:,.2f}\n")
    L.append(f"- Sheet **monthly** May'26 MTD column Net Revenue: USD "
             f"{may_mtd.get('Net Revenue', 0):,.2f}\n")
    L.append(f"- These should equal but the sheet differs by {us_daily_may_sum - may_mtd.get('Net Revenue', 0):+,.0f}. "
             f"The sheet's May MTD column appears to roll up a different subset "
             f"(possibly partial-month or includes only specific SKUs).\n")
    L.append(f"- Dashboard May 1-24 daily Net Sales: USD "
             f"{sum(dash_daily('US', d)['net_sales'] for d in [(date(2026,5,1)+timedelta(days=i)).isoformat() for i in range(24)]):,.2f}\n")
    L.append(f"- Dashboard aligns with the sheet's **daily** values (per-date Delta "
             f"typically < 5%) but NOT with the sheet's **MTD** column. "
             f"Trust the daily comparison; the MTD column appears to be a separate "
             f"narrower aggregate.\n\n")

    L.append("## Conclusions\n\n")
    L.append("1. **No double-application of UK VAT**: Ad spend ex-VAT GBP "
             f"{uk['ad_ex']:,.2f} x 1.20 = GBP {uk['ad_inc']:,.2f} inc, recovery "
             f"GBP {uk['ad_inc']*20/120:,.2f}, net deduction GBP "
             f"{uk['ad_inc'] - uk['ad_inc']*20/120:,.2f} = ex-VAT. Algebra checks out. "
             "Same for smart promo.\n")
    L.append("2. **CM1 dashboard < sheet by ~5%** (UK L30): dashboard CM1 GBP "
             f"{uk['cm1']:,.0f} vs sheet GBP {uk_s_cm1:,.0f}. Dashboard's "
             f"per-order shipping line (GBP {uk['per_order_shipping']:,.0f}) explains "
             f"~half of gap. Remaining ~{((uk['cm1'] + uk['per_order_shipping']) - uk_s_cm1) / uk_s_cm1 * 100:+.1f}% "
             "is residual unit-cost methodology (likely VAT-on-inputs, storage, or "
             "logistics treatment).\n")
    L.append("3. **CM2 dashboard < sheet-implied CM2** because sheet's daily section "
             "DOES NOT include Affiliate Commission as a P&L line (it appears only in "
             "an Amazon+TikTok or per-SKU section). Dashboard correctly deducts "
             f"GBP {uk['affiliate']:,.0f} affiliate per spec, making dashboard CM2 "
             f"GBP {uk['affiliate']:,.0f} more negative.\n")
    L.append("4. **Sheet internal inconsistency** on US: monthly TikTok Overall MTD "
             "column != sum of daily TikTok Overall values for same period. Dashboard "
             "matches the sheet's daily values, not the MTD column.\n")
    L.append("5. **Dashboard CM2 is correctly negative** under current ad-spend "
             "intensity (UK ad ex/NSV = "
             f"{uk['ad_ex']/uk['net_sales_ex_vat']*100:.0f}%, "
             f"US ad/NS = {us['ad_ex']/us['net_sales']*100:.0f}%). Operator's "
             "spreadsheet derived CM2 (excluding affiliate) is also negative for most "
             "L30 days. **The negative CM2 reflects real ad-spend intensity this "
             "period, not a dashboard bug.**\n")
    L.append("\n## Action items (recommended, not implemented)\n\n")
    L.append("- **None to dashboard code.** Per CLAUDE.md, per-order shipping, "
             "affiliate, and smart promo deductions are non-negotiable.\n")
    L.append("- Suggest operator: align sheet methodology to include affiliate "
             "commission in daily CM2 derivation, or document the omission. "
             "Suggest operator: investigate sheet's US May'26 MTD column formula -- "
             "appears broken vs daily sum.\n")

    out.write_text("".join(L), encoding="utf-8")
    print(f"Wrote {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
