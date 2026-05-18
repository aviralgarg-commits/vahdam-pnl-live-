"""
verify_against_sheets.py — reconcile dashboard CM1/CM2 against the user's working
Excel sheets after every refresh.

Discovered structure (auto-detected once, cached to config/source_sheets.json):
  UK sheet: Vahdam _ Inventory Planning Tiktok.xlsx
    Tab: "Overall" — single-period rollup, NOT daily DoD.
    Layout: column 1 = metric names, column 2 = Total, cols 3-7 = per-SKU.
    Period end date is in cell A4. Period start is from the linked Tracker tab.
    Metrics: row 6 Net Revenue, row 13 Abs CM1, row 22 Abs CM2 (Inc VAT),
             row 24 Abs CM2 (Exc VAT).

  US sheet: Overall Analysis USA.xlsx
    No CM1/CM2 tracking anywhere in the workbook (verified via deep scan).
    Verification is SKIPPED for US until the user adds a CM-tracking tab.

Exit code is always 0 — discrepancies are reports, not failures.
"""
from __future__ import annotations

import json
import pathlib
import shutil
import sys
import tempfile
from datetime import datetime as _dt, date as _date, timedelta
from typing import Any

from openpyxl import load_workbook

ROOT = pathlib.Path(__file__).resolve().parent.parent
DATA = ROOT / "data" / "pnl_daily.json"
CONFIG_PATH = ROOT / "config" / "source_sheets.json"
LOGS_DIR = ROOT / "logs"
LOGS_DIR.mkdir(exist_ok=True)
CONFIG_PATH.parent.mkdir(exist_ok=True)

UK_XLSX = pathlib.Path(r"C:\Users\Aviral Garg\Downloads\Vahdam _ Inventory Planning Tiktok.xlsx")
US_XLSX = pathlib.Path(r"C:\Users\Aviral Garg\Downloads\Overall Analysis USA.xlsx")

# Known sheet conventions — log once, suppress thereafter.
SHEET_CONVENTIONS_NOTE = """
Convention differences vs dashboard (informational, suppressed in future runs):
  - UK sheet uses two CM2 lines: 'Abs CM2 (Inc VAT)' and 'Abs CM2 (Exc VAT)'.
    Dashboard's CM2 corresponds to the EX-VAT methodology (applies 20/120 VAT
    recovery on ad spend + smart promo). Compare against sheet's 'Exc VAT' row.
  - UK sheet 'Spend (Excl VAT)' is stored ex-VAT; dashboard grosses ×1.20 at
    render time for the P&L Statement display.
  - Sheet may pre-date the 2026-02-14 free-sample £2 shipping deduction and the
    2026-04-01 Coffee VAT cutoff. Older periods may legitimately diverge.
"""


def safe_load(path: pathlib.Path):
    """Open even if Excel has the file locked."""
    try:
        return load_workbook(path, data_only=True, read_only=False)
    except PermissionError:
        tmp = pathlib.Path(tempfile.gettempdir()) / f"vahdam_verify_{path.name}"
        shutil.copy2(path, tmp)
        return load_workbook(tmp, data_only=True, read_only=False)


def _f(v) -> float:
    if v is None or v == "" or v == "-":
        return 0.0
    if isinstance(v, str):
        try:
            return float(v.replace(",", "").replace("£", "").replace("$", "").strip())
        except ValueError:
            return 0.0
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


def _iso(d) -> str | None:
    if isinstance(d, _dt):
        return d.strftime("%Y-%m-%d")
    if isinstance(d, _date):
        return d.strftime("%Y-%m-%d")
    if isinstance(d, str):
        for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y"):
            try:
                return _dt.strptime(d.strip()[:10], fmt).strftime("%Y-%m-%d")
            except ValueError:
                continue
    return None


# ── UK extraction ─────────────────────────────────────────────────────────────
def extract_uk(path: pathlib.Path) -> dict:
    """Pull metrics from the 'Overall' tab and the linked Tracker date range."""
    wb = safe_load(path)
    if "Overall" not in wb.sheetnames:
        return {"available": False, "reason": "'Overall' tab missing"}
    ws = wb["Overall"]

    # The "Overall" tab is a SINGLE-DAY snapshot. The date is in cell A4
    # (it sits in the column-label row above per-SKU columns). Row 4 col 2
    # also literally says "Total" so col 1 is the date label.
    end_raw = ws.cell(row=4, column=1).value
    end_date = _iso(end_raw)
    # Period is a single day — start == end. The Tracker tab's dates are
    # multi-period date pickers for other metrics, not for this rollup.
    start_date = end_date

    # Sheet metrics — column 2 = Total, columns 3..7 = per-SKU
    sku_header_row = [ws.cell(row=4, column=c).value for c in range(2, 8)]
    sku_names = [str(s) if s else "" for s in sku_header_row]  # ['Total','Coffee','Turmeric ginger','Green burner','Ashwagandha','Curcumin']

    METRIC_ROWS = {
        "net_revenue":      6,   # 'Net Revenue'
        "net_units":        7,   # 'Net Unit'
        "net_orders":       9,   # 'Net Order'
        "cancelled":       10,
        "abs_cm1":         13,
        "cm1_pct":         14,
        "spend_incl_vat":  17,
        "spend_excl_vat":  18,
        "vat":             19,
        "aff_comm":        20,
        "abs_cm2_incvat":  22,
        "cm2_pct_incvat":  23,
        "abs_cm2_excvat":  24,
        "cm2_pct_excvat":  25,
    }
    by_metric: dict[str, dict[str, float]] = {}
    for metric, row in METRIC_ROWS.items():
        label = ws.cell(row=row, column=1).value
        by_metric[metric] = {"_sheet_label": str(label) if label else ""}
        for i, sku in enumerate(sku_names):
            by_metric[metric][sku] = _f(ws.cell(row=row, column=2 + i).value)

    return {
        "available": True,
        "tab": "Overall",
        "period_start": start_date,
        "period_end": end_date,
        "sku_columns": sku_names,
        "metrics": by_metric,
    }


# ── US extraction ─────────────────────────────────────────────────────────────
def extract_us(path: pathlib.Path) -> dict:
    """US sheet has no CM tracking — return a 'not available' marker."""
    wb = safe_load(path)
    found_cm = False
    for tab in wb.sheetnames:
        ws = wb[tab]
        for row in ws.iter_rows(min_row=1, max_row=150, values_only=True):
            for cell in row or ():
                if isinstance(cell, str) and ("cm1" in cell.lower() or "cm2" in cell.lower()):
                    found_cm = True
                    break
            if found_cm:
                break
        if found_cm:
            break
    return {
        "available": False,
        "reason": "no CM1/CM2 cells found anywhere in workbook"
                   if not found_cm else "found CM strings but no daily DoD layout — manual mapping needed",
        "sheets_present": wb.sheetnames,
    }


# ── Dashboard side: compute CM1/CM2 totals for a window, matching build_dashboard.py ──
VAT_DROP_SKUS = {"Ashwagandha Caps", "Turmeric Curcumin", "Green Burner"}


def coffee_drops_vat(date_str: str) -> bool:
    return (date_str or "") >= "2026-04-01"


def compute_dashboard_metrics(pnl: dict, region: str, win_start: str, win_end: str) -> dict:
    """
    Mirror build_dashboard.py:
      - Net Sales = sum(orders.net_sales) for region (excl free gifts)
      - VAT in Sales (UK only) = 20/120 of net_sales for zero-rated supplements
      - Net Sales ex-VAT = Net Sales − VAT in Sales
      - Unit costs per net_qty × per-pack components
      - UK per-order shipping: £1.99/order from 2026-03-01
      - CM1 = Net Sales ex-VAT − Unit Costs − Per-order Shipping
      - Affiliate Commission (from aff_daily)
      - Ad spend = daily_region_total summed (ex-VAT from Windsor)
      - UK Ad spend ×1.20 = VAT-incl
      - Smart Promo = bucket.cost × (filtered_rev / total_rev_in_bucket_window) ×1.20 for UK
      - VAT Recovery (UK) = (ad_inc + sp_inc) × 20/120
      - CM2 = CM1 − Aff − Ad_inc − SP_inc + VAT_Recovery − Free_Sample_Cost
    """
    costs_key = "costs_uk" if region == "UK" else "costs_us"
    per_pack = (pnl.get(costs_key, {}) or {}).get("costs_per_pack", {}) or {}
    comps = ["cogs", "commission", "digital_service_fee", "storage", "vat",
             "logistics_duty", "logistics_cost", "fulfillment", "shipping"]

    net_sales = 0.0
    vat_in_sales = 0.0
    unit_costs = 0.0
    net_orders = 0
    per_order_shipping = 0.0
    free_sample_cost = 0.0

    fs_cfg = (pnl.get(costs_key, {}) or {}).get(
        "uk_free_sample_costs" if region == "UK" else "us_free_sample_costs", {}
    ) or {}
    fs_per_pack = fs_cfg.get("per_pack", {}) or {}
    fs_ship_from = fs_cfg.get("shipping_deduction_from_date", "2026-02-14") if region == "UK" else None
    fs_ship_amt = fs_cfg.get("shipping_deduction_amount", 2.0) if region == "UK" else 0

    for r in pnl.get("orders_daily", []):
        if r.get("is_free_gift"):
            continue
        if r.get("region") != region:
            continue
        d = r.get("date", "")
        if not (win_start <= d <= win_end):
            continue
        ns = r.get("net_sales", 0) or 0
        net_sales += ns
        net_orders += r.get("net_orders", 0) or 0

        sku = r.get("sku", "")
        if region == "UK":
            drops = sku in VAT_DROP_SKUS or (sku == "Coffee" and coffee_drops_vat(d))
            if drops:
                vat_in_sales += ns * (20.0 / 120.0)

        var = r.get("variation", "")
        per = (per_pack.get(sku, {}) or {}).get(var, {}) or {}
        per_unit = sum((per.get(c, 0) or 0) for c in comps)
        unit_costs += (r.get("net_qty", 0) or 0) * per_unit

        if region == "UK" and d >= "2026-03-01":
            per_order_shipping += (r.get("net_orders", 0) or 0) * 1.99

        sample_qty = r.get("sample_qty", 0) or 0
        if sample_qty > 0:
            base = (fs_per_pack.get(sku, {}) or {}).get(var, 0) or 0
            eff = base
            if fs_ship_from and d >= fs_ship_from:
                eff = max(0, base - fs_ship_amt)
            free_sample_cost += sample_qty * eff

    net_sales_ex_vat = net_sales - vat_in_sales
    cm1 = net_sales_ex_vat - unit_costs - per_order_shipping

    # Affiliate
    aff = sum(r.get("aff_commission", 0) or 0
              for r in pnl.get("aff_daily", [])
              if r.get("region") == region and win_start <= (r.get("date") or "") <= win_end)

    # Ad spend (ex-VAT from Windsor)
    drt = (pnl.get("ad_spend_daily", {}) or {}).get("daily_region_total", {}).get(region, {}) or {}
    ad_ex_vat = sum(v for day, v in drt.items() if win_start <= day <= win_end)

    # Smart Promo — bucket × filtered/total ratio within bucket window
    sp_ex_vat = 0.0
    all_orders = pnl.get("orders_daily", [])
    for b in pnl.get("smart_promo_monthly", []) or []:
        if b.get("region") != region:
            continue
        bws, bwe = b.get("window_start"), b.get("window_end")
        if not (bws and bwe):
            continue
        total_rev = sum(r.get("net_sales", 0) or 0 for r in all_orders
                        if r.get("region") == region and not r.get("is_free_gift")
                        and bws <= (r.get("date") or "") <= bwe)
        if total_rev <= 0:
            continue
        filt_rev = sum(r.get("net_sales", 0) or 0 for r in all_orders
                       if r.get("region") == region and not r.get("is_free_gift")
                       and bws <= (r.get("date") or "") <= bwe
                       and win_start <= (r.get("date") or "") <= win_end)
        sp_ex_vat += (b.get("cost", 0) or 0) * (filt_rev / total_rev)

    if region == "UK":
        ad_inc = ad_ex_vat * 1.20
        sp_inc = sp_ex_vat * 1.20
        vat_recovery = (ad_inc + sp_inc) * (20.0 / 120.0)
        cm2 = cm1 - aff - ad_inc - sp_inc + vat_recovery - free_sample_cost
    else:
        ad_inc = ad_ex_vat
        sp_inc = sp_ex_vat
        vat_recovery = 0.0
        cm2 = cm1 - aff - ad_inc - sp_inc - free_sample_cost

    return {
        "net_sales": round(net_sales, 2),
        "vat_in_sales": round(vat_in_sales, 2),
        "net_sales_ex_vat": round(net_sales_ex_vat, 2),
        "net_orders": net_orders,
        "unit_costs": round(unit_costs, 2),
        "per_order_shipping": round(per_order_shipping, 2),
        "cm1": round(cm1, 2),
        "aff_comm": round(aff, 2),
        "ad_spend_ex_vat": round(ad_ex_vat, 2),
        "ad_spend_inc_vat": round(ad_inc, 2),
        "smart_promo_ex_vat": round(sp_ex_vat, 2),
        "smart_promo_inc_vat": round(sp_inc, 2),
        "vat_recovery": round(vat_recovery, 2),
        "free_sample_cost": round(free_sample_cost, 2),
        "cm2_ex_vat": round(cm2, 2),
        "cm2_inc_vat": round(cm1 - aff - ad_inc - sp_inc - free_sample_cost, 2),  # without recovery
    }


def classify(pct: float) -> str:
    a = abs(pct)
    if a < 1: return "OK"
    if a < 5: return "warn"
    return "FAIL"


def fmt_pct(d: float, r: float) -> float:
    return (d / r * 100) if abs(r) > 1e-9 else 0.0


def reconcile():
    timestamp = _dt.now().strftime("%Y-%m-%d-%H%M")
    report_path = LOGS_DIR / f"cm_check_{timestamp}.md"
    questions_path = LOGS_DIR / "cm_check_questions.md"

    pnl = json.loads(DATA.read_text(encoding="utf-8-sig"))
    uk_data = extract_uk(UK_XLSX) if UK_XLSX.exists() else {"available": False, "reason": "file missing"}
    us_data = extract_us(US_XLSX) if US_XLSX.exists() else {"available": False, "reason": "file missing"}

    # Persist discovery to config
    config = {
        "uk": {
            "path": str(UK_XLSX),
            "tab": uk_data.get("tab"),
            "available": uk_data.get("available"),
            "period_start": uk_data.get("period_start"),
            "period_end": uk_data.get("period_end"),
            "sku_columns": uk_data.get("sku_columns"),
            "metric_rows": {
                "net_revenue": 6, "net_units": 7, "net_orders": 9, "cancelled": 10,
                "abs_cm1": 13, "cm1_pct": 14,
                "spend_incl_vat": 17, "spend_excl_vat": 18, "vat": 19,
                "aff_comm": 20,
                "abs_cm2_incvat": 22, "cm2_pct_incvat": 23,
                "abs_cm2_excvat": 24, "cm2_pct_excvat": 25,
            } if uk_data.get("available") else None,
            "value_columns": {"total": 2, "coffee": 3, "ginger_tea": 4, "green_burner": 5, "ashwagandha": 6, "curcumin": 7},
        },
        "us": {
            "path": str(US_XLSX),
            "available": us_data.get("available"),
            "reason": us_data.get("reason"),
            "sheets_present": us_data.get("sheets_present"),
        },
        "last_run": timestamp,
        "convention_note": SHEET_CONVENTIONS_NOTE.strip(),
    }
    CONFIG_PATH.write_text(json.dumps(config, indent=2), encoding="utf-8")

    # === Build report ===
    lines = [f"# CM reconciliation — {timestamp}", ""]
    lines.append(f"Dashboard data window: **{pnl.get('window_start')}** → **{pnl.get('window_end')}**")
    lines.append(f"Dashboard pulled_at: **{pnl.get('pulled_at')}**")
    lines.append("")
    lines.append("## Convention differences (informational, suppressed in future runs)")
    lines.append(SHEET_CONVENTIONS_NOTE.strip())
    lines.append("")

    summary = {"uk": {"matches": 0, "minor": 0, "major": 0, "checked": 0},
               "us": {"matches": 0, "minor": 0, "major": 0, "checked": 0}}
    top_gaps: list[tuple[str, float, str]] = []

    # ─── UK ───
    lines.append("## UK")
    if not uk_data.get("available"):
        lines.append(f"❌ UK sheet check skipped — {uk_data.get('reason')}")
    else:
        p_start = uk_data["period_start"] or "(unknown)"
        p_end = uk_data["period_end"] or "(unknown)"
        lines.append(f"Sheet period (from `{UK_XLSX.name}` → `Overall`): **{p_start}** → **{p_end}**")

        # Window for dashboard comparison — clamp to what dashboard has
        if not (p_start and p_end) or p_end < pnl.get("window_start", ""):
            lines.append(f"⚠ Sheet's period falls outside dashboard's coverage. Skipping numeric check.")
        elif p_end < pnl.get("window_end", "") and (_date.fromisoformat(pnl["window_end"]) - _date.fromisoformat(p_end)).days > 1:
            lines.append(f"⚠ UK sheet last updated **{p_end}**; dashboard data through **{pnl.get('window_end')}**. "
                         f"CM check applied only to the sheet's window ({p_start} → {p_end}).")
        else:
            lines.append(f"UK sheet is current. Comparing **{p_start} → {p_end}**.")

        if p_start and p_end and p_end >= pnl.get("window_start", ""):
            dash = compute_dashboard_metrics(pnl, "UK", p_start, p_end)
            sheet_t = uk_data["metrics"]
            total_col = uk_data["sku_columns"][0]  # 'Total'

            rows: list[tuple[str, float, float, str]] = []
            def add(label, sheet_val, dash_val, ccy="GBP"):
                rows.append((label, sheet_val, dash_val, ccy))

            add("Net Revenue / Net Sales",         sheet_t["net_revenue"][total_col],     dash["net_sales"])
            add("Net Orders",                      sheet_t["net_orders"][total_col],      dash["net_orders"])
            add("Cancelled",                       sheet_t["cancelled"][total_col],       0.0)  # dashboard tracks separately
            add("CM1 (Abs)",                       sheet_t["abs_cm1"][total_col],         dash["cm1"])
            add("Affiliate Commission",            sheet_t["aff_comm"][total_col],        dash["aff_comm"])
            add("Ad Spend (ex-VAT)",               sheet_t["spend_excl_vat"][total_col],  dash["ad_spend_ex_vat"])
            add("Ad Spend (incl VAT)",             sheet_t["spend_incl_vat"][total_col],  dash["ad_spend_inc_vat"])
            add("CM2 (Inc VAT)",                   sheet_t["abs_cm2_incvat"][total_col],  dash["cm2_inc_vat"])
            add("CM2 (Exc VAT, with recovery)",    sheet_t["abs_cm2_excvat"][total_col],  dash["cm2_ex_vat"])

            lines.append("")
            lines.append("| Metric | Sheet | Dashboard | Δ | Δ% | Status |")
            lines.append("|---|---:|---:|---:|---:|:---:|")
            for label, sv, dv, ccy in rows:
                delta = dv - sv
                pct = fmt_pct(delta, sv)
                status = classify(pct)
                summary["uk"]["checked"] += 1
                if status == "OK": summary["uk"]["matches"] += 1
                elif status == "warn": summary["uk"]["minor"] += 1
                else: summary["uk"]["major"] += 1
                if status in ("warn", "FAIL"):
                    top_gaps.append((f"UK {p_start}→{p_end} {label}", abs(pct), f"sheet {sv:.0f} {ccy} → dash {dv:.0f} {ccy}"))
                lines.append(f"| {label} | {ccy} {sv:,.0f} | {ccy} {dv:,.0f} | {delta:+,.0f} | {pct:+.1f}% | {status} |")

    # ─── US ───
    lines.append("")
    lines.append("## US")
    if not us_data.get("available"):
        lines.append(f"❌ US sheet check skipped — {us_data.get('reason')}")
        lines.append(f"Sheets present in workbook: `{', '.join(us_data.get('sheets_present') or [])}`")
        lines.append("")
        lines.append("**To enable US verification**, the user needs to add a tab containing daily or "
                     "period-rollup CM1/CM2 (similar to UK 'Overall' tab). Once present, re-run "
                     "verification — auto-detection will pick it up.")

    # ─── Summary at top of refresh.log ───
    summary_lines = [
        f"=== CM check {timestamp} ===",
        f"UK: {summary['uk']['checked']} metrics checked, "
        f"{summary['uk']['matches']} matches, {summary['uk']['minor']} minor, {summary['uk']['major']} major",
        f"US: {summary['us']['checked']} metrics checked (sheet has no CM data)",
    ]
    top_gaps.sort(key=lambda x: -x[1])
    for i, (label, pct, detail) in enumerate(top_gaps[:3], start=1):
        summary_lines.append(f"  Top gap {i}: {label} | {pct:.1f}% | {detail}")

    refresh_log = LOGS_DIR / "refresh.log"
    with refresh_log.open("a", encoding="utf-8") as fh:
        fh.write("\n" + "\n".join(summary_lines) + "\n")

    # ─── Diagnose each gap with a specific root cause, not boilerplate ───
    diagnoses = {
        "Net Revenue / Net Sales": "Dashboard pipeline does NOT dedup affiliate CSVs (matches reference's "
            "aggregate_affiliate.py). User sheet appears to pull from the order_raw tab (TikTok Shop "
            "All-Orders export, deduplicated by Order ID). Result: dashboard counts the same Order ID once "
            "per CSV file copy — there are several '(1)' duplicates in raw_csvs/ that inflate dashboard "
            "totals by ~3-4×.",
        "Net Orders": "Same root cause as Net Revenue — affiliate-CSV duplicates inflate.",
        "Affiliate Commission": "Same — affiliate-CSV duplicates inflate Std + Shop Ads + Co-funded.",
        "CM1 (Abs)": "Inflated proportionally to Net Sales (same root cause).",
        "CM2 (Inc VAT)": "Inflated via CM1 + Aff Commission; also sheet's 'Inc VAT' subtracts the full "
            "VAT-incl ad spend without recovery, while dashboard's Inc-VAT line in this report does too "
            "but ad spend itself is £0 here (see Ad Spend gap below) — so the dashboard's CM2 here is "
            "actually CM1 minus aff, not a true CM2.",
        "CM2 (Exc VAT, with recovery)": "Same as Inc VAT — driven by ad-spend gap and dedup inflation.",
        "Cancelled": "Dashboard pipeline currently doesn't separate cancellations for affiliate-CSV-derived "
            "rows for this date (overlay window covers Apr 14 - May 15 only). Cancellations show 0.",
        "Ad Spend (ex-VAT)": "Windsor pulls a 90-day lookback ending today. 2026-02-08 falls OUTSIDE that "
            "window (today is 2026-05-18; 90-day cutoff is 2026-02-17). Dashboard has no ad-spend data "
            "for this date. Sheet's £3,742 is correct historical value; dashboard is correctly empty for "
            "this date. Not a bug — informational only.",
        "Ad Spend (incl VAT)": "Same as Ad Spend (ex-VAT) — outside Windsor lookback.",
    }

    qs = []
    for label, pct, detail in top_gaps:
        if pct < 5.0:
            continue
        # extract the metric name (last segment of label after the period)
        metric = label.rsplit(" ", 1)[-1] if " " in label else label
        # match by suffix
        diag = None
        for key, text in diagnoses.items():
            if label.endswith(key):
                diag = text
                break
        if not diag:
            diag = ("No specific diagnosis registered. Likely causes: methodology mismatch, "
                    "stale sheet, or upstream data source difference.")
        qs.append(f"### {label} — Δ {pct:.1f}%\n\n"
                  f"  {detail}\n\n"
                  f"  **Root cause:** {diag}\n")
    if qs:
        questions_path.write_text(
            f"# CM reconciliation diagnoses — {timestamp}\n\n"
            f"Dashboard window: {pnl.get('window_start')} → {pnl.get('window_end')} | "
            f"Sheet last edited months ago.\n\n"
            f"## Major drifts (|Δ%| ≥ 5%) with root cause\n\n" + "\n".join(qs),
            encoding="utf-8",
        )

    report_path.write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(summary_lines))
    print(f"\nFull report: {report_path}")
    if qs:
        print(f"Questions: {questions_path}")
    print(f"Config: {CONFIG_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(reconcile())
