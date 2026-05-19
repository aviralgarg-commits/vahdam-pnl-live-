"""
refresh_daily.py — Daily refresh orchestrator (no Windsor).

Pipeline:
  0. ensure_chrome_running  — make sure Chrome is up on debug port 9222
  1. scrape_orders.py       — UK + US "All Order" CSVs into raw_csvs/
  2. scrape_ads.py          — UK + US GMV Max dashboard snapshots
  3. scrape_affiliate.py    — UK + US affiliate-orders CSVs into raw_csvs/
  4. scrape_smart_promo.py  — UK + US Smart Promotion buckets -> data/smart_promo_monthly.json
  5. aggregate_affiliate.py — rebuild aff_daily section of pnl_daily.json from raw_csvs/
  6. build_dashboard.py     — render public/index.html
  7. git add/commit/push    — Vercel auto-deploys on push
  8. verify_against_sheets  — diff CM1/CM2 vs user's local xlsx; emit logs/cm_check_*.md

Run manually: python scripts/refresh_daily.py
Scheduled:    refresh_daily.bat (Task Scheduler A @ 11:00 Europe/London, B @ 15:00 America/Los_Angeles)
"""

from __future__ import annotations

import datetime as _dt
import pathlib
import subprocess
import sys
import time
import traceback
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

LOG_DIR = ROOT / "logs"
LOG_DIR.mkdir(exist_ok=True)
REFRESH_LOG = LOG_DIR / "refresh.log"


def log_line(msg: str) -> None:
    line = f"[{_dt.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {msg}"
    print(line)
    with REFRESH_LOG.open("a", encoding="utf-8") as fh:
        fh.write(line + "\n")


def run_step(name: str, fn):
    print(f"\n{'='*60}")
    print(f"STEP: {name}")
    print(f"{'='*60}")
    t0 = time.time()
    try:
        result = fn()
        elapsed = time.time() - t0
        log_line(f"OK   {name} ({elapsed:.1f}s)")
        return result
    except Exception as e:
        elapsed = time.time() - t0
        log_line(f"FAIL {name} ({elapsed:.1f}s): {e}")
        traceback.print_exc()
        return None


def ensure_chrome_running() -> bool:
    """Make sure Chrome is listening on CDP port 9222. Launch via the .bat
    if not. Returns True if reachable, False otherwise — scrapers handle
    the False case gracefully (skip + log)."""
    url = "http://localhost:9222/json/version"
    try:
        urllib.request.urlopen(url, timeout=2)
        print("  Chrome already running on debug port 9222.")
        return True
    except Exception:
        pass
    bat = ROOT / "scripts" / "launch_chrome_debug.bat"
    if not bat.exists():
        log_line("WARN launch_chrome_debug.bat missing; scrapers will skip.")
        return False
    print(f"  Chrome not running on :9222 — launching {bat.name}")
    subprocess.Popen([str(bat)], shell=True)
    for _ in range(15):
        time.sleep(1)
        try:
            urllib.request.urlopen(url, timeout=2)
            print("  Chrome now reachable on debug port 9222.")
            return True
        except Exception:
            continue
    log_line("WARN Chrome did not become reachable within 15s.")
    return False


def git_commit_and_push() -> bool:
    """Auto-commit + push so Vercel rebuilds. No-op when nothing to commit."""
    try:
        # Stage only the files this pipeline produces; never mass-add.
        files = [
            "data/pnl_daily.json",
            "data/smart_promo_monthly.json",
            "public/index.html",
            "raw_csvs",
            "seller_center_snapshots",
            "logs",
        ]
        subprocess.run(["git", "add", "--"] + files, cwd=ROOT, check=False)
        status = subprocess.run(["git", "diff", "--cached", "--quiet"],
                                cwd=ROOT, check=False)
        if status.returncode == 0:
            print("  No staged changes — nothing to commit.")
            return True
        msg = f"refresh: daily data pull {_dt.date.today().isoformat()}"
        subprocess.run(["git", "commit", "-m", msg], cwd=ROOT, check=True)
        subprocess.run(["git", "push"], cwd=ROOT, check=True)
        return True
    except subprocess.CalledProcessError as e:
        log_line(f"git step failed: {e}")
        return False


def main():
    print("\n" + "=" * 60)
    print("Vahdam P&L Daily Refresh")
    print(f"Time: {_dt.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)

    run_step("Ensure Chrome (CDP port 9222) is up", ensure_chrome_running)

    # Each scraper is independent — failure in one doesn't abort the others.
    # Each scraper writes its own outputs (CSVs in raw_csvs/ or JSON in
    # data/ + seller_center_snapshots/) and returns 0/1; we don't pass
    # data around in-memory.
    def _maybe(modname: str):
        try:
            mod = __import__(modname)
            return mod.main()
        except ImportError:
            log_line(f"SKIP {modname} (module not present yet)")
            return None

    run_step("Scrape orders (Seller Center)",       lambda: _maybe("scrape_orders"))
    run_step("Scrape ads (Seller Center)",          lambda: _maybe("scrape_ads"))
    run_step("Scrape affiliate (Seller Center)",    lambda: _maybe("scrape_affiliate"))
    run_step("Scrape Smart Promotion",              lambda: _maybe("scrape_smart_promo"))

    # Re-aggregate affiliate CSVs into pnl_daily.json's aff_daily section.
    run_step("Aggregate affiliate CSVs", lambda: _maybe("aggregate_affiliate"))

    # Build the static dashboard HTML.
    def do_build():
        import importlib
        import build_dashboard
        importlib.reload(build_dashboard)
    run_step("Build dashboard HTML", do_build)

    # Push to GitHub → Vercel rebuilds.
    run_step("git commit + push (triggers Vercel)", git_commit_and_push)

    # Verify CM1/CM2 vs user's local xlsx (no failure on mismatch — just logs).
    def do_verify():
        import importlib
        try:
            import verify_against_sheets
            importlib.reload(verify_against_sheets)
            return verify_against_sheets.reconcile()
        except ImportError:
            log_line("SKIP verify_against_sheets (module not present yet)")
            return None
    run_step("Verify against source sheets", do_verify)

    print("\n" + "=" * 60)
    print("Refresh complete. Dashboard: public/index.html")
    print(f"Local server: http://localhost:8000/")
    print(f"Vercel:       https://vahdam-pnl-live.vercel.app/")
    print("=" * 60)


if __name__ == "__main__":
    main()
