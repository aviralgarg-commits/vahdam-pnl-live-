"""
fetch_google_sheets.py — pull the live "TikTok Overall DoD" tabs from the user's
two working Google Sheets and refresh data/source_sheet_snapshot.json.

Requires a Google service account JSON at config/google_credentials.json.
The service account email must be granted Viewer access on BOTH sheets.

If credentials are missing or unreadable, this script logs a warning and exits 0
(the existing manually-transcribed snapshot continues to be the source of truth).

SETUP (one-time, ~5 min):
  1) https://console.cloud.google.com → Create project (or pick existing)
  2) APIs & Services → Library → enable "Google Sheets API"
  3) APIs & Services → Credentials → Create Credentials → Service Account
       Role: not required (we'll grant Sheet-level access)
  4) Service Account → Keys → Add Key → JSON → download
  5) Move the downloaded JSON to:
       C:\\Users\\Aviral Garg\\vahdam-pnl-live\\config\\google_credentials.json
  6) Copy the "client_email" from the JSON.
     Open both Google Sheets → Share → paste that email → Viewer → Send.
  7) Run scripts/fetch_google_sheets.py manually to verify.
"""
from __future__ import annotations

import json
import pathlib
import re
import sys
from datetime import datetime as _dt

ROOT = pathlib.Path(__file__).resolve().parent.parent
CONFIG_PATH = ROOT / "config" / "google_credentials.json"
SNAPSHOT = ROOT / "data" / "source_sheet_snapshot.json"

UK_SHEET_ID = "1cLjkuNQf4NB0iTuPb9SB6MJ1ELIf3jFVurj37P80I2I"
US_SHEET_ID = "1kqOvsf4EFsay5oK6oD5o2hBAkwT4NZCYBOEKRYeByq4"
TAB_NAME = "TikTok Overall DoD"

# Header-row index where metric labels live (col A) and the date column header lives.
# Both sheets follow the same layout: row 2 has dates across columns C onwards;
# col A from row 4 down has metric names. Adjust if the user changes layout.
DATE_HEADER_ROW = 2  # 1-indexed
METRIC_NAME_COL = 1  # column A

# Map sheet metric labels (case-insensitive substring match) -> snapshot keys
# These are PER-REGION because columns differ slightly UK vs US.
UK_METRIC_MAP = {
    "Net Revenue":          "net_rev",
    "Net Unit":             "net_unit",
    "Net Order":            "net_order",
    "Cancelled":            "cancelled",
    "Actual Commission":    "actual_comm",
    "Other Fix Charges":    "other_fix",
    "Abs CM1":              "abs_cm1",
    "CM1 %":                "cm1_pct",
    "Free Samples":         "free_samples",
    "Spend (Incl VAT)":     "spend_incl_vat",
    "Spend (Excl VAT)":     "spend_excl_vat",
    "Affiliated Commission":"aff_comm",
    "Abs CM2":              "abs_cm2",
    "CM2 %":                "cm2_pct",
    "Ad_spend":             "ad_spend",
}
US_METRIC_MAP = {
    "Net Revenue":          "net_rev",
    "Net Unit":             "net_unit",
    "Net Order":            "net_order",
    "Cancelled":            "cancelled",
    "Actual Commission":    "actual_comm",
    "Other Fix Charges":    "other_fix",
    "Abs CM1":              "abs_cm1",
    "CM1 %":                "cm1_pct",
    "Free Samples":         "free_samples",
    "Spend+Live":           "spend_live",
    "Affiliated Commission":"aff_comm",
    "Abs CM2":              "abs_cm2",
    "CM2 %":                "cm2_pct",
    "Ad_spend_total":       "ad_spend_total",
}


def _f(v) -> float:
    """Money/number cell -> float. Handles £/$/%, commas, parens."""
    if v is None or v == "":
        return 0.0
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v).strip().replace(",", "").replace("£", "").replace("$", "")
    if s.endswith("%"):
        try:
            return float(s[:-1]) / 100.0
        except ValueError:
            return 0.0
    if s.startswith("(") and s.endswith(")"):
        s = "-" + s[1:-1]
    try:
        return float(s)
    except ValueError:
        return 0.0


def _parse_date(v) -> str | None:
    """Cell value (string or sheets-date-int) -> 'YYYY-MM-DD'."""
    if v in (None, ""):
        return None
    if isinstance(v, str):
        v = v.strip()
        for fmt in ("%Y-%m-%d", "%-m/%-d/%Y", "%m/%d/%Y", "%d/%m/%Y", "%m/%-d/%Y", "%-m/%d/%Y"):
            try:
                return _dt.strptime(v, fmt).strftime("%Y-%m-%d")
            except ValueError:
                continue
        # tolerate "5/17/2026"
        m = re.match(r"^(\d{1,2})[/-](\d{1,2})[/-](\d{4})$", v)
        if m:
            mm, dd, yy = m.groups()
            try:
                return _dt(int(yy), int(mm), int(dd)).strftime("%Y-%m-%d")
            except ValueError:
                return None
        return None
    if isinstance(v, (int, float)):
        # Sheets serial date: days since 1899-12-30
        from datetime import date as _date, timedelta as _td
        try:
            return (_date(1899, 12, 30) + _td(days=int(v))).strftime("%Y-%m-%d")
        except (OverflowError, ValueError):
            return None
    return None


def fetch_tab(sheet_id: str, tab_name: str, metric_map: dict) -> dict:
    """Return {date_iso: {metric_key: value}} for the daily columns on the tab."""
    import gspread
    from google.oauth2.service_account import Credentials

    scopes = ["https://www.googleapis.com/auth/spreadsheets.readonly"]
    creds = Credentials.from_service_account_file(str(CONFIG_PATH), scopes=scopes)
    gc = gspread.authorize(creds)
    sh = gc.open_by_key(sheet_id)
    ws = sh.worksheet(tab_name)
    grid = ws.get_all_values()  # list of rows, each a list of strings

    if not grid or len(grid) < DATE_HEADER_ROW + 1:
        return {}

    # Find the date columns by scanning the date header row
    header_row = grid[DATE_HEADER_ROW - 1]
    date_cols: list[tuple[int, str]] = []
    for col_idx, cell in enumerate(header_row):
        iso = _parse_date(cell)
        if iso and iso.startswith("20"):
            date_cols.append((col_idx, iso))

    # Find the row index for each desired metric (substring match, first hit wins)
    metric_rows: dict[str, int] = {}
    for row_idx, row in enumerate(grid):
        if not row or not row[METRIC_NAME_COL - 1]:
            continue
        label = str(row[METRIC_NAME_COL - 1]).strip().lower()
        for sheet_label, key in metric_map.items():
            if key in metric_rows:
                continue
            if sheet_label.lower() == label or sheet_label.lower() in label:
                metric_rows[key] = row_idx

    # Build the daily snapshot
    daily: dict[str, dict[str, float]] = {}
    for col_idx, iso in date_cols:
        bucket: dict[str, float] = {}
        for key, row_idx in metric_rows.items():
            if col_idx >= len(grid[row_idx]):
                continue
            bucket[key] = _f(grid[row_idx][col_idx])
        if bucket:
            daily[iso] = bucket
    return daily


def main() -> int:
    if not CONFIG_PATH.exists():
        print(f"WARN: Google Sheets credentials not found at {CONFIG_PATH}")
        print(f"  Manual snapshot at {SNAPSHOT} continues to be source of truth.")
        print(f"  See scripts/fetch_google_sheets.py docstring for setup steps.")
        return 0

    try:
        import gspread  # noqa: F401
    except ImportError:
        print("WARN: gspread not installed. Run: pip install gspread google-auth")
        return 0

    print(f"Fetching live Google Sheets via {CONFIG_PATH.name}...")
    try:
        uk_daily = fetch_tab(UK_SHEET_ID, TAB_NAME, UK_METRIC_MAP)
        us_daily = fetch_tab(US_SHEET_ID, TAB_NAME, US_METRIC_MAP)
    except Exception as e:
        print(f"ERROR fetching from Google Sheets: {e}")
        print(f"  Falling back to manual snapshot at {SNAPSHOT}.")
        return 0

    # Load existing snapshot, replace daily blocks, preserve monthly + meta
    existing = json.loads(SNAPSHOT.read_text(encoding="utf-8-sig")) if SNAPSHOT.exists() else {}
    existing.setdefault("_meta", {})
    existing["_meta"]["source"] = "Google Sheets live (via service account)"
    existing["_meta"]["captured_at"] = _dt.now().strftime("%Y-%m-%d %H:%M")
    existing["_meta"]["uk_sheet"] = f"https://docs.google.com/spreadsheets/d/{UK_SHEET_ID}"
    existing["_meta"]["us_sheet"] = f"https://docs.google.com/spreadsheets/d/{US_SHEET_ID}"
    existing.setdefault("UK", {})["daily"] = uk_daily
    existing.setdefault("US", {})["daily"] = us_daily

    SNAPSHOT.write_text(json.dumps(existing, indent=2), encoding="utf-8")
    print(f"Updated snapshot: UK {len(uk_daily)} days, US {len(us_daily)} days")
    print(f"Latest dates: UK {max(uk_daily) if uk_daily else 'none'}, "
          f"US {max(us_daily) if us_daily else 'none'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
