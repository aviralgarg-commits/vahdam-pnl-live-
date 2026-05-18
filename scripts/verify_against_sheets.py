"""
verify_against_sheets.py — reconcile dashboard CM1/CM2 against the user's
working Google Sheets (UK TikTok+Amazon, USA TikTok+Amazon — "TikTok Overall DoD" tab).

Source-of-truth values are transcribed in data/source_sheet_snapshot.json.
Run reconciliation after every dashboard refresh; write report + questions log.

Re-capture the snapshot whenever the user updates the live sheets — see
the "_meta" block in source_sheet_snapshot.json for the source URLs.
"""
from __future__ import annotations

import json
import pathlib
import sys
from datetime import datetime as _dt

ROOT = pathlib.Path(__file__).resolve().parent.parent
DATA = ROOT / "data" / "pnl_daily.json"
SHEET_SNAPSHOT = ROOT / "data" / "source_sheet_snapshot.json"
LOGS_DIR = ROOT / "logs"
LOGS_DIR.mkdir(exist_ok=True)


def classify(pct: float) -> str:
    a = abs(pct)
    if a < 1: return "OK"
    if a < 5: return "warn"
    return "FAIL"


def pct_of(delta: float, base: float) -> float:
    return (delta / base * 100) if abs(base) > 1e-9 else 0.0


def dashboard_daily(pnl: dict, region: str, date: str) -> dict:
    """Pull dashboard's totals for a single date + region."""
    net_sales = 0.0
    net_orders = 0
    cancelled = 0
    samples = 0
    net_qty = 0
    refunds = 0.0

    for r in pnl.get("orders_daily", []):
        if r.get("date") != date or r.get("region") != region or r.get("is_free_gift"):
            continue
        net_sales += r.get("net_sales", 0) or 0
        net_orders += r.get("net_orders", 0) or 0
        cancelled += r.get("cancelled_orders", 0) or 0
        samples += r.get("sample_orders", 0) or 0
        net_qty += r.get("net_qty", 0) or 0
        refunds += r.get("refund", 0) or 0

    aff_comm = sum((r.get("aff_commission", 0) or 0)
                    for r in pnl.get("aff_daily", [])
                    if r.get("date") == date and r.get("region") == region)

    ad_ex_vat = (pnl.get("ad_spend_daily", {}) or {}).get("daily_region_total", {}).get(region, {}).get(date, 0) or 0

    return {
        "net_sales":  round(net_sales, 0),
        "net_orders": int(net_orders),
        "cancelled":  int(cancelled),
        "free_samples": int(samples),
        "net_qty":    int(net_qty),
        "refunds":    round(refunds, 0),
        "aff_comm":   round(aff_comm, 0),
        "ad_spend_ex_vat": round(ad_ex_vat, 0),
        "ad_spend_inc_vat_uk": round(ad_ex_vat * 1.20, 0) if region == "UK" else round(ad_ex_vat, 0),
    }


# Map sheet's keys → dashboard's keys (so we compare the same thing)
COMPARISON_PAIRS_UK = [
    ("Net Revenue",         "net_rev",        "net_sales",         "GBP"),
    ("Net Orders",          "net_order",      "net_orders",        ""),
    ("Net Units",           "net_unit",       "net_qty",           ""),
    ("Cancelled Orders",    "cancelled",      "cancelled",         ""),
    ("Free Samples",        "free_samples",   "free_samples",      ""),
    ("Affiliated Comm",     "aff_comm",       "aff_comm",          "GBP"),
    ("Ad Spend (ex-VAT)",   "spend_excl_vat", "ad_spend_ex_vat",   "GBP"),
    ("Ad Spend (incl VAT)", "spend_incl_vat", "ad_spend_inc_vat_uk","GBP"),
    ("Ad Spend total (sheet 'ad_spend')", "ad_spend", "ad_spend_inc_vat_uk", "GBP"),
]
COMPARISON_PAIRS_US = [
    ("Net Revenue",         "net_rev",        "net_sales",         "USD"),
    ("Net Orders",          "net_order",      "net_orders",        ""),
    ("Net Units",           "net_unit",       "net_qty",           ""),
    ("Cancelled Orders",    "cancelled",      "cancelled",         ""),
    ("Free Samples",        "free_samples",   "free_samples",      ""),
    ("Affiliated Comm",     "aff_comm",       "aff_comm",          "USD"),
    ("Ad Spend total",      "ad_spend_total", "ad_spend_ex_vat",   "USD"),
]


def reconcile():
    timestamp = _dt.now().strftime("%Y-%m-%d-%H%M")
    pnl = json.loads(DATA.read_text(encoding="utf-8-sig"))
    snap = json.loads(SHEET_SNAPSHOT.read_text(encoding="utf-8-sig"))

    report_path = LOGS_DIR / f"cm_check_{timestamp}.md"
    questions_path = LOGS_DIR / "cm_check_questions.md"

    lines = [
        f"# CM reconciliation vs Google Sheets — {timestamp}",
        "",
        f"Dashboard window: **{pnl.get('window_start')}** → **{pnl.get('window_end')}**  ",
        f"Source: live Google Sheets ('TikTok Overall DoD' tabs, snapshot taken {snap['_meta']['captured_at']})  ",
        f"UK sheet: {snap['_meta']['uk_sheet']}  ",
        f"US sheet: {snap['_meta']['us_sheet']}",
        "",
    ]

    summary = {"uk": {"OK": 0, "warn": 0, "FAIL": 0}, "us": {"OK": 0, "warn": 0, "FAIL": 0}}
    top_gaps: list[tuple] = []

    for region_key, region, pairs in (("UK", "UK", COMPARISON_PAIRS_UK), ("US", "US", COMPARISON_PAIRS_US)):
        lines.append(f"## {region} — daily reconciliation")
        lines.append("")
        sheet_dates = sorted(snap[region_key]["daily"].keys(), reverse=True)
        # Build a header row
        header = "| Metric | " + " | ".join(sheet_dates) + " |"
        sep    = "|---|" + "|".join(["---:"] * len(sheet_dates)) + "|"
        lines.append(header)
        lines.append(sep)

        for label, sheet_key, dash_key, ccy in pairs:
            row_sheet = ["**" + label + " (sheet)**"]
            row_dash  = [label + " (dash)"]
            row_pct   = [label + " Δ%"]
            for d in sheet_dates:
                sv = snap[region_key]["daily"][d].get(sheet_key)
                dash = dashboard_daily(pnl, region, d)
                dv = dash.get(dash_key, 0)
                sv_num = sv if isinstance(sv, (int, float)) else 0
                dv_num = dv if isinstance(dv, (int, float)) else 0
                row_sheet.append(f"{sv_num:,.0f}")
                row_dash.append(f"{dv_num:,.0f}")
                if sv_num and abs(sv_num) > 1e-6:
                    p = pct_of(dv_num - sv_num, sv_num)
                    status = classify(p)
                    summary[region.lower()][status] += 1
                    marker = "✓" if status == "OK" else ("⚠" if status == "warn" else "✗")
                    row_pct.append(f"{p:+.1f}% {marker}")
                    if status != "OK":
                        top_gaps.append((region, d, label, sv_num, dv_num, p, ccy))
                else:
                    row_pct.append("—")
            lines.append("| " + " | ".join(row_sheet) + " |")
            lines.append("| " + " | ".join(row_dash) + " |")
            lines.append("| " + " | ".join(row_pct) + " |")
            lines.append("|" + " |"*(len(sheet_dates)+1))
        lines.append("")

    # Top gaps + diagnoses
    top_gaps.sort(key=lambda x: -abs(x[5]))
    lines.append("## Top discrepancies (by |Δ%|)")
    lines.append("")
    lines.append("| Region | Date | Metric | Sheet | Dashboard | Δ | Δ% |")
    lines.append("|---|---|---|---:|---:|---:|---:|")
    for region, d, label, sv, dv, p, ccy in top_gaps[:15]:
        lines.append(f"| {region} | {d} | {label} | {ccy} {sv:,.0f} | {ccy} {dv:,.0f} | {dv-sv:+,.0f} | {p:+.1f}% |")

    # ─── Summary line for refresh.log ───
    sumline = [
        f"=== CM check vs Google Sheets {timestamp} ===",
        f"UK: {summary['uk']['OK']} matches, {summary['uk']['warn']} minor, {summary['uk']['FAIL']} major",
        f"US: {summary['us']['OK']} matches, {summary['us']['warn']} minor, {summary['us']['FAIL']} major",
    ]
    for region, d, label, sv, dv, p, ccy in top_gaps[:3]:
        sumline.append(f"  Top gap: {region} {d} {label} | sheet {ccy}{sv:,.0f} → dash {ccy}{dv:,.0f} | {p:+.1f}%")

    with (LOGS_DIR / "refresh.log").open("a", encoding="utf-8") as fh:
        fh.write("\n" + "\n".join(sumline) + "\n")

    report_path.write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(sumline))
    print(f"\nFull report: {report_path}")
    return 0


if __name__ == "__main__":
    sys.exit(reconcile())
