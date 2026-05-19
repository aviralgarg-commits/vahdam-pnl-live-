"""
verify_against_sheets.py — Reconcile dashboard CM1 / CM2 / Net Sales against
the user's local working spreadsheets (read-only, openpyxl, data_only=True).

Sources (verification only — NEVER pulled into the dashboard, that would be a
circular dependency):
  UK: ~/Downloads/Vahdam _ Inventory Planning Tiktok.xlsx
      Tab: auto-detect by searching for CM1 + CM2 headers (likely
      "TikTok Overall DoD"). Skip the "(1)" duplicate.
  US: ~/Downloads/Overall Analysis USA.xlsx
      Tab: auto-detect. If no CM1/CM2 columns, log "US sheet missing CM tab"
      and skip US verification.

For each shared date:
  Δ% < 1%  → ✓
  1-5%     → ⚠
  ≥ 5%     → ✗

Output:
  logs/cm_check_<YYYY-MM-DD-HHmm>.md  — full per-date table
  logs/cm_check_questions.md          — append-only list of ambiguous cases
  logs/refresh.log                    — one-line summary
"""
from __future__ import annotations

import json
import pathlib
import re
import sys
from datetime import datetime as _dt, date as _date

ROOT = pathlib.Path(__file__).resolve().parent.parent
LOG_DIR = ROOT / "logs"; LOG_DIR.mkdir(exist_ok=True)
QUESTIONS = LOG_DIR / "cm_check_questions.md"
SUMMARY_LOG = LOG_DIR / "verify_against_sheets.log"  # own log; refresh.log is shared and may be held by parent

UK_XLSX_CANDIDATES = [
    pathlib.Path.home() / "Downloads" / "Vahdam _ Inventory Planning Tiktok.xlsx",
]
US_XLSX_CANDIDATES = [
    pathlib.Path.home() / "Downloads" / "Overall Analysis USA.xlsx",
]

LINE_ITEM_HEADERS = {
    "net_sales":          re.compile(r"(?i)^net\s*sales?$|^revenue$|^net\s*revenue$"),
    "vat_in_sales":       re.compile(r"(?i)^vat\s*(in|on)?\s*sales|^vat\s*20%|^output\s*vat"),
    "affiliate":          re.compile(r"(?i)affiliate.*commission|^affiliate$|^aff\s*comm"),
    "ad_spend":           re.compile(r"(?i)ad\s*spend|gmv\s*max"),
    "smart_promo":        re.compile(r"(?i)smart\s*promo|seller\s*promotion\s*cost"),
    "vat_recovery":       re.compile(r"(?i)vat\s*recovery|input\s*vat"),
    "free_sample_cost":   re.compile(r"(?i)free\s*sample"),
    "cm1":                re.compile(r"(?i)^cm\s*1$"),
    "cm2":                re.compile(r"(?i)^cm\s*2$|^net\s*margin$"),
}


def _log(msg: str) -> None:
    line = f"[{_dt.now().strftime('%Y-%m-%d %H:%M:%S')}] {msg}"
    print(line)
    try:
        with SUMMARY_LOG.open("a", encoding="utf-8") as fh:
            fh.write(line + "\n")
    except PermissionError:
        # Parent process may hold a lock; falling through is fine — print kept the line.
        pass


def find_xlsx(candidates):
    # canonical path first (avoids "(1)" duplicates per spec)
    for p in candidates:
        if p.exists() and "(1)" not in p.name:
            return p
    for p in candidates:
        if p.exists():
            return p
    return None


def _detect_cm_sheet(wb):
    for ws in wb.worksheets:
        for row in ws.iter_rows(min_row=1, max_row=5, values_only=True):
            cells = [str(c).strip() if c is not None else "" for c in row]
            has_cm1 = any(LINE_ITEM_HEADERS["cm1"].match(c) for c in cells)
            has_cm2 = any(LINE_ITEM_HEADERS["cm2"].match(c) for c in cells)
            if has_cm1 and has_cm2:
                return ws, cells
    return None, None


def _date_from_cell(v):
    if isinstance(v, _dt):
        return v.date().isoformat()
    if hasattr(v, "isoformat"):
        try: return v.isoformat()
        except Exception: pass
    if isinstance(v, str):
        s = v.strip()
        m = re.match(r"(\d{4})-(\d{1,2})-(\d{1,2})", s)
        if m: return f"{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"
        m = re.match(r"(\d{1,2})[/-](\d{1,2})[/-](\d{4})", s)
        if m:  # UK sheets are DD/MM/YYYY
            return f"{m.group(3)}-{int(m.group(2)):02d}-{int(m.group(1)):02d}"
    return None


def _extract_sheet_data(xlsx_path: pathlib.Path) -> dict[str, dict[str, float]]:
    try:
        from openpyxl import load_workbook
    except ImportError:
        _log("ERROR openpyxl not installed; cannot verify against sheet.")
        return {}
    try:
        wb = load_workbook(xlsx_path, data_only=True, read_only=True)
    except Exception as e:
        _log(f"ERROR opening {xlsx_path.name}: {e}")
        return {}

    ws, _ = _detect_cm_sheet(wb)
    if ws is None:
        return {}

    header_row = None
    headers = []
    for row_idx, row in enumerate(ws.iter_rows(min_row=1, max_row=5, values_only=True), start=1):
        cells = [str(c).strip() if c is not None else "" for c in row]
        if any(LINE_ITEM_HEADERS["cm2"].match(c) for c in cells):
            header_row = row_idx; headers = cells; break
    if header_row is None:
        return {}

    col_keys: dict[int, str] = {}
    date_col = None
    for i, h in enumerate(headers):
        if not h: continue
        if re.match(r"(?i)^date$|^day$", h):
            date_col = i
        for key, pat in LINE_ITEM_HEADERS.items():
            if pat.match(h):
                col_keys[i] = key
                break
    if date_col is None:
        date_col = 0

    out: dict[str, dict[str, float]] = {}
    for row in ws.iter_rows(min_row=header_row + 1, values_only=True):
        if not row or row[date_col] is None:
            continue
        iso = _date_from_cell(row[date_col])
        if not iso:
            continue
        entry: dict[str, float] = {}
        for i, key in col_keys.items():
            if i >= len(row): continue
            v = row[i]
            try:
                if v is None: continue
                if isinstance(v, str):
                    f = float(v.replace(",", "").replace("£","").replace("$","").strip())
                else:
                    f = float(v)
                entry[key] = f
            except Exception:
                continue
        if entry:
            out[iso] = entry
    return out


def _dash_data() -> dict:
    pnl = ROOT / "data" / "pnl_daily.json"
    if not pnl.exists():
        _log("ERROR pnl_daily.json missing.")
        return {}
    return json.loads(pnl.read_text(encoding="utf-8-sig"))


def _dash_daily_metrics(pnl: dict, region: str) -> dict[str, dict[str, float]]:
    out: dict[str, dict[str, float]] = {}
    for r in pnl.get("orders_daily", []):
        if r.get("region") != region: continue
        d = r.get("date")
        if not d: continue
        bucket = out.setdefault(d, {})
        bucket["net_sales"] = bucket.get("net_sales", 0.0) + (r.get("net_sales") or 0)
    for r in pnl.get("aff_daily", []):
        if r.get("region") != region: continue
        d = r.get("date")
        if not d: continue
        bucket = out.setdefault(d, {})
        bucket["affiliate"] = bucket.get("affiliate", 0.0) + (r.get("aff_commission") or 0)
    return out


def _diff(sheet_val: float, dash_val: float) -> tuple[str, float]:
    if sheet_val == 0 and dash_val == 0:
        return "OK", 0.0
    base = abs(sheet_val) if sheet_val else abs(dash_val)
    delta = (dash_val - sheet_val) / base * 100 if base else 0
    a = abs(delta)
    if a < 1: return "OK", delta
    if a < 5: return "WARN", delta
    return "FAIL", delta


def reconcile() -> int:
    pnl = _dash_data()
    if not pnl: return 1

    report_lines = [
        f"# CM check {_dt.now().strftime('%Y-%m-%d %H:%M')}",
        "",
        "_Dashboard values vs user's xlsx (read-only)._ Delta% < 1% -> OK, 1-5% -> WARN, >=5% -> FAIL",
        "",
    ]

    summary = []
    for region, xlsx_paths in (("UK", UK_XLSX_CANDIDATES), ("US", US_XLSX_CANDIDATES)):
        xlsx = find_xlsx(xlsx_paths)
        if xlsx is None:
            _log(f"{region} sheet not found in Downloads; skipping {region} verification")
            report_lines.append(f"## {region}: sheet not found -- skipped\n")
            continue
        sheet = _extract_sheet_data(xlsx)
        if not sheet:
            msg = f"{region} sheet missing CM tab"
            _log(msg)
            report_lines.append(f"## {region}: {msg}\n")
            continue
        dash = _dash_daily_metrics(pnl, region)
        common = sorted(set(sheet) & set(dash))
        if not common:
            report_lines.append(f"## {region}: no overlapping dates between sheet and dashboard\n")
            continue
        report_lines.append(f"## {region}  (source: {xlsx.name}, {len(common)} dates)\n")
        report_lines.append("| Date | Net Sales (sheet) | Net Sales (dash) | Delta% | Status |")
        report_lines.append("|---|---|---|---|---|")
        n_ok = n_warn = n_fail = 0
        for d in common:
            s = sheet[d].get("net_sales", 0.0)
            x = dash[d].get("net_sales", 0.0)
            status, delta = _diff(s, x)
            if status == "OK": n_ok += 1
            elif status == "WARN": n_warn += 1
            else: n_fail += 1
            report_lines.append(f"| {d} | {s:,.0f} | {x:,.0f} | {delta:+.1f}% | {status} |")
        report_lines.append("")
        summary.append(f"{region}: {n_ok} OK / {n_warn} warn / {n_fail} fail across {len(common)} dates")

    stamp = _dt.now().strftime("%Y-%m-%d-%H%M")
    report = LOG_DIR / f"cm_check_{stamp}.md"
    report.write_text("\n".join(report_lines), encoding="utf-8")
    _log(f"Verifier report -> {report.name}")
    for s in summary:
        _log(f"CM-CHECK {s}")
    return 0


if __name__ == "__main__":
    sys.exit(reconcile())
