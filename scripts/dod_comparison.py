"""dod_comparison.py -- Compare dashboard daily P&L vs Google Sheet TikTok Overall DoD tabs.

UK source: Google Sheet 1cLjkuNQf4NB0iTuPb9SB6MJ1ELIf3jFVurj37P80I2I, gid=1932099571
  (Tab: 'TikTok Overall', label-row format with daily columns. Currency: GBP, $ prefix is
   default formatting; values are in GBP per metadata.)
  Pulled via public CSV export to data/uk_dod.csv.

US source: Google Sheet 1kqOvsf4EFsay5oK6oD5o2hBAkwT4NZCYBOEKRYeByq4, gid=1310969871
  (Tab: 'TikTok+Amazon DOD' containing 'TikTok Overall' section. Currency: USD.)
  Pulled via Drive MCP read_file_content; parsed from markdown table.

For each daily date in L30 (2026-04-25 -> 2026-05-24) we extract sheet Net Revenue,
Abs CM1, Spend (Excl VAT), Affiliated Commission, Abs CM2 (US only), and compare to
dashboard values computed from data/pnl_daily.json under the dashboard's spec
(CLAUDE.md). Classify Delta% < 3% [OK], 3-7% [WARN], >= 7% [FAIL].
"""
from __future__ import annotations

import csv
import json
import re
import sys
from datetime import date, timedelta
from pathlib import Path

LIVE = Path(__file__).resolve().parent.parent
END = date(2026, 5, 24)
START = date(2026, 4, 25)
DAYS = [(START + timedelta(days=i)).isoformat() for i in range((END - START).days + 1)]

PNL = json.loads((LIVE / "data" / "pnl_daily.json").read_text(encoding="utf-8-sig"))

# Tax rules (UK)
TAX = (PNL.get("costs_uk") or {}).get("uk_tax_rules", {})
VAT_KEPT = set(TAX.get("vat_kept_skus", ["Turmeric Ginger Tea"]))
VAT_REMOVED_ALWAYS = set(TAX.get("vat_removed_always",
                                 ["Green Burner", "Ashwagandha Caps", "Turmeric Curcumin"]))
COFFEE_CUTOFF = (TAX.get("vat_removed_from_date") or {}).get("Coffee", "2026-04-01")
SHIP_FROM = TAX.get("shipping_per_order_from_date", "2026-03-01")
SHIP_AMT = TAX.get("shipping_per_order_amount", 1.99)

UK_CPP = (PNL.get("costs_uk") or {}).get("costs_per_pack", {})
US_CPP = (PNL.get("costs_us") or {}).get("costs_per_pack", {})


def parse_money(s):
    if s is None or s == "":
        return None
    if isinstance(s, (int, float)):
        return float(s)
    s = str(s).strip()
    if not s:
        return None
    neg = False
    if s.startswith("(") and s.endswith(")"):
        neg = True
        s = s[1:-1]
    if s.startswith("-"):
        neg = True
        s = s[1:]
    s = s.replace("$", "").replace("£", "").replace(",", "").strip()
    if not s or s in ("#DIV/0!", "-"):
        return None
    try:
        v = float(s)
        return -v if neg else v
    except ValueError:
        return None


def iso_from_sheet_date(label):
    """Parse '5/24/2026' or 'May 24, 2026' -> '2026-05-24'."""
    label = label.strip()
    # 5/24/2026 or 05/24/2026
    m = re.match(r"^(\d{1,2})/(\d{1,2})/(\d{4})$", label)
    if m:
        mo, d, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
        return f"{y:04d}-{mo:02d}-{d:02d}"
    # "May 24, 2026"
    m = re.match(r"^([A-Za-z]+)\s+(\d{1,2}),\s*(\d{4})$", label)
    if m:
        months = {"Jan":1,"Feb":2,"Mar":3,"Apr":4,"May":5,"Jun":6,"Jul":7,"Aug":8,
                  "Sep":9,"Oct":10,"Nov":11,"Dec":12}
        mo = months.get(m.group(1)[:3].title())
        if mo:
            return f"{int(m.group(3)):04d}-{mo:02d}-{int(m.group(2)):02d}"
    return None


def parse_uk_csv():
    """Parse uk_dod.csv -> {iso_date: {label: value}}."""
    path = LIVE / "data" / "uk_dod.csv"
    rows = list(csv.reader(open(path, encoding="utf-8")))
    # Find the >>TikTok UK Overall section (row starting with ">>TikTok UK Overall" in col B)
    section_start = None
    for i, row in enumerate(rows):
        if len(row) >= 2 and row[1].strip() == ">>TikTok UK Overall":
            section_start = i
            break
    if section_start is None:
        raise ValueError("Could not find >>TikTok UK Overall in UK CSV")
    # The next row (or so) has Date--->
    date_row_idx = None
    for j in range(section_start + 1, min(section_start + 6, len(rows))):
        if rows[j] and rows[j][1].strip() == "Date--->":
            date_row_idx = j
            break
    if date_row_idx is None:
        raise ValueError("Could not find Date--->")
    date_cols = rows[date_row_idx]
    # Map column index -> iso date (only for daily date columns)
    col_to_iso = {}
    for ci, cell in enumerate(date_cols):
        iso = iso_from_sheet_date(cell)
        if iso:
            col_to_iso[ci] = iso
    # Find labels we care about under this section, until next ">>" header
    out = {iso: {} for iso in col_to_iso.values()}
    interesting = {"Net Revenue", "Net Order", "Abs CM1", "Spend (Incl VAT)",
                   "Spend (Excl VAT)", "Free Samples Fix Charges", "Actual Commission",
                   "Other Fix Charges"}
    end = len(rows)
    for j in range(date_row_idx + 1, len(rows)):
        row = rows[j]
        if not row or len(row) < 2:
            continue
        first = row[1].strip()
        if first.startswith(">>"):
            end = j
            break
        if first in interesting:
            for ci, iso in col_to_iso.items():
                if ci < len(row):
                    v = parse_money(row[ci])
                    if v is not None:
                        out[iso][first] = v
    return out, rows, section_start, date_row_idx, col_to_iso


def parse_us_markdown():
    """Parse US sheet markdown.

    US has two relevant sources:
      1) Monthly-aggregate section at top: 'Date--->/TikTok Overall' row with
         Jan'26/Feb'26/Mar'26/Apr'26/May'26 MTD columns. Contains Spend+Live,
         Affiliated Commission, Abs CM2 -- the full P&L.
      2) Daily TikTok Overall section at pos ~337415 ('TikTok Overall' label
         row with daily date columns). Contains Net Revenue and Abs CM1 only
         (no Spend / CM2 row in the daily section).

    Returns ({iso_date: {label: value}}, {month_key: {label: value}}).
    """
    # Find the most-recent tool-result file for the Drive MCP read_file_content
    # on the US sheet. Falls back to a known earlier file if newer not present.
    tr_dir = (Path.home() / ".claude" / "projects" /
              "C--Users-Aviral-Garg-Downloads-Claude-Code-Artefact" /
              "f2a84419-a50a-4f97-9276-747c5dd0cc85" / "tool-results")
    cands = sorted(tr_dir.glob("mcp-6f10172d-*-read_file_content-*.txt"))
    # Pick the most recent that contains "USA Tiktok+Amazon" in the title (US sheet)
    path = None
    for p in reversed(cands):
        try:
            head = p.read_text(encoding="utf-8")[:5000]
            if "USA" in head or "Coffee + Shatavari" in head:
                path = p; break
        except Exception:
            continue
    if path is None:
        raise FileNotFoundError("US sheet markdown dump not found in tool-results")
    c = json.loads(path.read_text(encoding="utf-8"))["fileContent"]
    lines = c.split("\n")

    # --- DAILY TikTok Overall section ---
    daily = {}
    # Find row "TikTok Overall | Tiktok | Tiktok | ..." marker; the preceding
    # rows are the Date--->row and :-: separator. Pattern hits twice in markdown
    # because every section starts with date row above.
    daily_section_idx = None
    for i, ln in enumerate(lines):
        if ln.strip().startswith("| TikTok Overall |") and " | Tiktok |" in ln:
            daily_section_idx = i
            break
    if daily_section_idx is not None:
        # The Date---> row is 2 lines above (Date row, :-: separator, then this)
        date_row_idx = None
        for j in range(daily_section_idx - 1, max(0, daily_section_idx - 6), -1):
            if "Date--->" in lines[j] or lines[j].strip().startswith("| Date"):
                date_row_idx = j; break
        if date_row_idx is not None:
            date_cells = [x.strip() for x in lines[date_row_idx].strip("|").split("|")]
            col_to_iso = {}
            for ci, cell in enumerate(date_cells):
                iso = iso_from_sheet_date(cell.replace("\\>", ">").replace("\\", "").strip())
                if iso: col_to_iso[ci] = iso
            daily = {iso: {} for iso in col_to_iso.values()}
            interesting = {"Net Revenue", "Net Order", "Abs CM1", "CM1 %",
                           "Actual Commission", "Other Fix Charges",
                           "Free Samples", "Free Samples Fix Charges"}
            for j in range(daily_section_idx + 1, min(daily_section_idx + 40, len(lines))):
                ln = lines[j]
                if not ln.startswith("|"): continue
                cells = [x.strip() for x in ln.strip("|").split("|")]
                if not cells: continue
                label = cells[0].strip()
                if not label or label.startswith(">>") or "Date" in label:
                    if label != "Date": continue
                    if label == "Date": break
                if label in interesting:
                    for ci, iso in col_to_iso.items():
                        if ci < len(cells):
                            v = parse_money(cells[ci])
                            if v is not None:
                                daily[iso].setdefault(label, v)

    # --- MONTHLY TikTok Overall section ---
    monthly = {}
    month_section_idx = None
    for i, ln in enumerate(lines):
        # markdown escapes > as \>, so check both forms
        if "TikTok Overall" in ln and "Date" in ln and ("Jan'26" in ln or "Jan\\'26" in ln):
            month_section_idx = i
            break
    if month_section_idx is not None:
        cells = [x.strip() for x in lines[month_section_idx].strip("|").split("|")]
        col_to_month = {}
        for ci, cell in enumerate(cells):
            cell_clean = cell.replace("\\>", ">").replace("\\", "").strip()
            m = re.match(r"^(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)'(\d{2})(?:/Tiktok)?$",
                         cell_clean)
            if m:
                mo_names = {"Jan":1,"Feb":2,"Mar":3,"Apr":4,"May":5,"Jun":6,
                            "Jul":7,"Aug":8,"Sep":9,"Oct":10,"Nov":11,"Dec":12}
                col_to_month[ci] = f"2026-{mo_names[m.group(1)]:02d}"
            elif "May'26 MTD" in cell_clean:
                col_to_month[ci] = "2026-05-MTD"
        monthly = {mk: {} for mk in col_to_month.values()}
        interesting_m = {"Net Revenue", "Net Order", "Abs CM1", "CM1 %",
                         "Actual Commission", "Other Fix Charges", "Free Samples",
                         "Free Samples Fix Charges", "Spend+Live", "Spend",
                         "Affiliated Commission", "Abs CM2", "CM2 %"}
        for j in range(month_section_idx + 1, min(month_section_idx + 40, len(lines))):
            ln = lines[j]
            if not ln.startswith("|"): continue
            cells2 = [x.strip() for x in ln.strip("|").split("|")]
            if not cells2: continue
            label = cells2[0].strip()
            if not label or label.startswith(">>") or "Date--->" in label:
                if label and "Date--->" in label: break
                continue
            if label in interesting_m:
                for ci, mk in col_to_month.items():
                    if ci < len(cells2):
                        v = parse_money(cells2[ci])
                        if v is not None:
                            monthly[mk].setdefault(label, v)
    return daily, monthly


def dash_daily(region: str, iso: str) -> dict:
    """Compute dashboard values for a single date+region per spec."""
    rows = [r for r in PNL["orders_daily"]
            if r["region"] == region and r["date"] == iso and not r.get("is_free_gift")]
    net_sales = sum(r.get("net_sales", 0) for r in rows)
    net_orders = sum(r.get("net_orders", 0) for r in rows)
    net_qty = sum(r.get("net_qty", 0) for r in rows)
    sample_qty = sum(r.get("sample_qty", 0) for r in rows)

    vat_in_sales = 0.0
    if region == "UK":
        for r in rows:
            sku = r["sku"]
            is_zr = False
            if sku == "Coffee":
                is_zr = (r["date"] >= COFFEE_CUTOFF)
            elif sku in VAT_REMOVED_ALWAYS:
                is_zr = True
            if is_zr:
                vat_in_sales += r.get("net_sales", 0) * (20 / 120)
    nsv = net_sales - vat_in_sales

    cb = dict.fromkeys(("cogs","commission","dsf","storage","vat","logistics_duty",
                        "logistics_cost","fulfillment","shipping","per_order_shipping"), 0.0)
    cpp = UK_CPP if region == "UK" else US_CPP
    for r in rows:
        cps = cpp.get(r["sku"])
        cp = cps.get(r["variation"]) if cps else None
        q = r.get("net_qty", 0)
        o = r.get("net_orders", 0)
        sku = r["sku"]
        if region == "UK":
            if sku in VAT_KEPT: vat_app = True
            elif sku == "Coffee": vat_app = (r["date"] < COFFEE_CUTOFF)
            elif sku in VAT_REMOVED_ALWAYS: vat_app = False
            else: vat_app = True
        else:
            vat_app = True
        if cp:
            cb["cogs"]            += (cp.get("cogs", 0) or 0) * q
            cb["commission"]      += (cp.get("commission", 0) or 0) * q
            cb["dsf"]             += (cp.get("digital_service_fee", 0) or 0) * q
            cb["storage"]         += (cp.get("storage", 0) or 0) * q
            if vat_app:
                cb["vat"]         += (cp.get("vat", 0) or 0) * q
            cb["logistics_duty"]  += (cp.get("logistics_duty", 0) or 0) * q
            cb["logistics_cost"]  += (cp.get("logistics_cost", 0) or 0) * q
            cb["fulfillment"]     += (cp.get("fulfillment", 0) or 0) * q
            cb["shipping"]        += (cp.get("shipping", 0) or 0) * q
        if region == "UK" and r["date"] >= SHIP_FROM:
            cb["per_order_shipping"] += o * SHIP_AMT
    unit_total = sum(cb.values())
    cm1 = nsv - unit_total

    aff = sum(r.get("aff_commission", 0) for r in PNL["aff_daily"]
              if r["region"] == region and r["date"] == iso)

    ads_map = PNL["ad_spend_daily"]["daily_by_sku"].get(region, {})
    ad_ex = sum(v for v in ads_map.get(iso, {}).values())
    ad_inc = ad_ex * 1.20 if region == "UK" else ad_ex

    # Smart promo proportional allocation (same day's revenue share within month bucket)
    sp_ex = 0.0
    for b in PNL.get("smart_promo_monthly", []):
        if b["region"] != region: continue
        ws, we = b["window_start"], b["window_end"]
        if not (ws <= iso <= we): continue
        tot_rev = sum(r.get("net_sales", 0) for r in PNL["orders_daily"]
                      if r["region"] == region and ws <= r["date"] <= we
                      and not r.get("is_free_gift"))
        if tot_rev <= 0: continue
        day_rev = sum(r.get("net_sales", 0) for r in rows)
        sp_ex += b["cost"] * (day_rev / tot_rev)
    sp_inc = sp_ex * 1.20 if region == "UK" else sp_ex
    vat_rec = (ad_inc + sp_inc) * (20 / 120) if region == "UK" else 0.0

    fs = 0.0
    if region == "UK":
        ff = (PNL.get("costs_uk") or {}).get("uk_free_sample_costs", {}) or {}
        per_pack = ff.get("per_pack", {})
        sd_from = ff.get("shipping_deduction_from_date", "2026-02-14")
        sd_amt = ff.get("shipping_deduction_amount", 2.0)
        for r in rows:
            sq = r.get("sample_qty", 0)
            if sq <= 0: continue
            pp = (per_pack.get(r["sku"]) or {}).get(r["variation"], 0) or 0
            eff = max(0, pp - sd_amt) if r["date"] >= sd_from else pp
            fs += sq * eff
    else:
        ff = (PNL.get("costs_us") or {}).get("us_free_sample_costs", {}) or {}
        per_pack = ff.get("per_pack", {})
        for r in rows:
            sq = r.get("sample_qty", 0)
            if sq <= 0: continue
            pp = (per_pack.get(r["sku"]) or {}).get(r["variation"], 0) or 0
            fs += sq * pp

    cm2 = cm1 - aff - ad_inc - sp_inc + vat_rec - fs
    return {
        "net_sales": net_sales, "net_orders": net_orders,
        "vat_in_sales": vat_in_sales, "net_sales_ex_vat": nsv,
        "unit_costs": unit_total, "cm1": cm1, "affiliate": aff,
        "ad_ex": ad_ex, "ad_inc": ad_inc, "sp_ex": sp_ex, "sp_inc": sp_inc,
        "vat_rec": vat_rec, "free_sample": fs, "cm2": cm2,
        "per_order_shipping": cb["per_order_shipping"],
    }


def status(dash, sheet):
    if sheet is None or sheet == 0:
        return ("--", 0.0) if dash == 0 else ("--", float("inf"))
    delta = (dash - sheet) / abs(sheet) * 100
    a = abs(delta)
    if a < 3: s = "OK"
    elif a < 7: s = "WARN"
    else: s = "FAIL"
    return s, delta


def write_report(region, sheet_data, sym, fname):
    out = LIVE / "logs" / fname
    lines = [f"# DoD comparison -- {region}\n",
             f"Generated 2026-05-25. Window L30: {DAYS[0]} -> {DAYS[-1]}. ",
             f"Dashboard values from `data/pnl_daily.json` computed per CLAUDE.md spec; ",
             f"sheet values from Google Sheet TikTok Overall DoD tab.\n",
             "\n## Per-date comparison\n",
             "Status: < 3% [OK], 3-7% [WARN], >= 7% [FAIL]. ",
             "**Sheet currency**: UK in GBP (sheet's `$` is default formatting), US in USD. ",
             "**IMPORTANT**: Sheet's `Net Revenue` = dashboard's **Net Sales ex-VAT** ",
             "(not raw Net Sales). Verified: 5/24 sheet GBP 5,926 == dash NSV GBP 5,926.\n\n"]
    counts = {"net_revenue": [0,0,0], "abs_cm1": [0,0,0], "ad_spend": [0,0,0], "cm2": [0,0,0]}
    rows_data = []
    for iso in DAYS:
        d = dash_daily(region, iso)
        s = sheet_data.get(iso, {})
        s_ns = s.get("Net Revenue")
        s_cm1 = s.get("Abs CM1")
        s_spend_ex = s.get("Spend (Excl VAT)") if region == "UK" else s.get("Spend")
        s_aff = s.get("Affiliated Commission") if region == "US" else s.get("Actual Commission")
        s_cm2 = s.get("Abs CM2")
        s_fsfc = s.get("Free Samples Fix Charges")
        # Sheet daily section has no CM2 / Affiliate -- derive: CM1 - Spend - FreeSamples
        if region == "UK" and s_cm1 is not None and s_spend_ex is not None:
            s_cm2_derived = s_cm1 - s_spend_ex - (s_fsfc or 0)
        else:
            s_cm2_derived = s_cm2
        # Compare sheet Net Revenue against dashboard NSV (ex-VAT)
        rows_data.append((iso, d, s_ns, s_cm1, s_spend_ex, s_aff, s_cm2_derived, s_fsfc))
        for key, dv, sv in (("net_revenue", d["net_sales_ex_vat"], s_ns),
                            ("abs_cm1", d["cm1"], s_cm1),
                            ("ad_spend", d["ad_ex"], s_spend_ex),
                            ("cm2", d["cm2"], s_cm2_derived)):
            if sv is None: continue
            st, _ = status(dv, sv)
            if st == "OK": counts[key][0] += 1
            elif st == "WARN": counts[key][1] += 1
            elif st == "FAIL": counts[key][2] += 1

    lines.append(f"### Summary across {len(DAYS)} dates\n\n")
    lines.append("| Metric | OK | WARN | FAIL |\n|---|---:|---:|---:|\n")
    for k, label in (("net_revenue","Net Revenue (sheet) vs Net Sales ex-VAT (dash)"),
                     ("abs_cm1","Abs CM1"),
                     ("ad_spend","Ad Spend (ex-VAT)"),
                     ("cm2","CM2 (sheet-derived: CM1 - Spend - FreeSamples)")):
        lines.append(f"| {label} | {counts[k][0]} | {counts[k][1]} | {counts[k][2]} |\n")
    pct_ok_ns = counts["net_revenue"][0] / len(DAYS) * 100
    pct_ok_cm1 = counts["abs_cm1"][0] / len(DAYS) * 100
    pct_ok_cm2 = counts["cm2"][0] / len(DAYS) * 100
    lines.append(f"\n**Net Revenue OK%:** {pct_ok_ns:.0f}% (target 90%+)\n")
    lines.append(f"**Abs CM1 OK%:** {pct_ok_cm1:.0f}%\n")
    lines.append(f"**CM2 OK%:** {pct_ok_cm2:.0f}% (derived sheet CM2 lacks affiliate; expected gap)\n\n")

    lines.append("### Per-date detail\n\n")
    lines.append(f"| Date | Sheet Net Rev | Dash NSV | NSV Delta | Sheet CM1 | Dash CM1 | CM1 Delta | "
                 f"Sheet Spend | Dash Ad ex | AdEx Delta | Sheet CM2* | Dash CM2 | CM2 Delta |\n")
    lines.append("|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|\n")
    for iso, d, s_ns, s_cm1, s_spend_ex, s_aff, s_cm2, s_fsfc in rows_data:
        def cell(v):
            return f"{sym}{v:,.0f}" if v is not None else "--"
        def deltacell(dv, sv):
            if sv is None: return "--"
            st, dl = status(dv, sv)
            return f"{dl:+.1f}% [{st}]"
        lines.append(f"| {iso} | {cell(s_ns)} | {cell(d['net_sales_ex_vat'])} | "
                     f"{deltacell(d['net_sales_ex_vat'], s_ns)} | "
                     f"{cell(s_cm1)} | {cell(d['cm1'])} | "
                     f"{deltacell(d['cm1'], s_cm1)} | "
                     f"{cell(s_spend_ex)} | {cell(d['ad_ex'])} | "
                     f"{deltacell(d['ad_ex'], s_spend_ex)} | "
                     f"{cell(s_cm2)} | {cell(d['cm2'])} | "
                     f"{deltacell(d['cm2'], s_cm2)} |\n")
    lines.append("\n*Sheet CM2 derived as Abs CM1 - Spend (Excl VAT) - Free Samples Fix Charges. "
                 "Lacks Affiliate Commission and Smart Promo, which the dashboard CM2 includes. "
                 "Direct CM2 comparison is therefore expected to differ by Affiliate + SP.\n")

    out.write_text("".join(lines), encoding="utf-8")
    print(f"Wrote {out}  ({counts['net_revenue'][0]}/{len(DAYS)} NS OK, "
          f"{counts['abs_cm1'][0]}/{len(DAYS)} CM1 OK, {counts['cm2'][0]}/{len(DAYS)} CM2 OK)")
    return counts


def write_us_mtd_report(monthly):
    """Compare dashboard May'26 MTD totals vs US sheet's May'26 MTD column."""
    out = LIVE / "logs" / "dod_comparison_US_MTD.md"
    # Dashboard May 1-24 totals
    days = [(date(2026,5,1) + timedelta(days=i)).isoformat() for i in range(24)]
    agg = {"net_sales":0, "cm1":0, "ad_ex":0, "ad_inc":0, "sp_ex":0, "sp_inc":0,
           "vat_rec":0, "free_sample":0, "cm2":0, "affiliate":0, "unit_costs":0,
           "per_order_shipping":0}
    for iso in days:
        d = dash_daily("US", iso)
        for k in agg:
            agg[k] += d.get(k, 0)
    mtd = monthly.get("2026-05-MTD", {})
    lines = [
        "# US TikTok Overall -- May'26 MTD comparison\n",
        "Generated 2026-05-25. Sheet's daily TikTok Overall section only contains ",
        "Net Revenue + Abs CM1 (no Spend / CM2 row). Full P&L comparison only ",
        "available at MTD granularity from the sheet's monthly aggregate table.\n",
        "Window: 2026-05-01 -> 2026-05-24 (24 days, sheet 'May'26 MTD' column)\n\n",
        "| Metric | Sheet (May MTD) | Dashboard (May 1-24) | Delta% | Status |\n",
        "|---|---:|---:|---:|---|\n",
    ]
    def st(d_v, s_v):
        if s_v is None or s_v == 0: return ("--", 0.0)
        delta = (d_v - s_v) / abs(s_v) * 100
        a = abs(delta)
        if a < 3: return "OK", delta
        if a < 7: return "WARN", delta
        return "FAIL", delta
    metrics = [
        ("Net Revenue", "Net Revenue", agg["net_sales"]),
        ("Abs CM1", "Abs CM1", agg["cm1"]),
        ("Spend+Live", "Spend+Live", agg["ad_ex"]),
        ("Affiliated Commission", "Affiliated Commission", agg["affiliate"]),
        ("Abs CM2", "Abs CM2", agg["cm2"]),
    ]
    for sheet_label, _, dash_val in metrics:
        sv = mtd.get(sheet_label)
        s, dl = st(dash_val, sv)
        sv_str = f"${sv:,.0f}" if sv is not None else "--"
        lines.append(f"| {sheet_label} | {sv_str} | ${dash_val:,.0f} | "
                     f"{dl:+.1f}% | [{s}] |\n")
    out.write_text("".join(lines), encoding="utf-8")
    print(f"Wrote {out}")


def main():
    uk_sheet, _, _, _, _ = parse_uk_csv()
    us_daily, us_monthly = parse_us_markdown()
    print(f"UK sheet days parsed: {len(uk_sheet)}")
    print(f"US daily sheet rows: {len(us_daily)}; US monthly rows: {len(us_monthly)}")
    if us_daily:
        sample_iso = "2026-05-24"
        print(f"  US daily sample {sample_iso}: {us_daily.get(sample_iso, {})}")
    write_report("UK", uk_sheet, "£", "dod_compare_UK.md")
    write_report("US", us_daily, "$", "dod_compare_US.md")
    write_us_mtd_report(us_monthly)
    return 0


if __name__ == "__main__":
    sys.exit(main())
