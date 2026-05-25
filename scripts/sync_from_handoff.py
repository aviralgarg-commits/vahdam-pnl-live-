"""
sync_from_handoff.py -- Daily deploy hook.

The Cowork scheduled task "vahdam-pnl-3pm-refresh" updates the handoff folder
at 3 PM IST. This script runs at 3:30 PM IST on this machine and:
  1. Checks the handoff pnl_daily_REFERENCE.json is from today (else logs
     "Handoff stale, skipping deploy" and exits 0).
  2. Copies handoff/data/pnl_daily_REFERENCE.json -> live/data/pnl_daily.json
  3. Rebuilds public/index.html via build_dashboard.py
  4. git add -A && git commit && git push (Vercel auto-deploys on push)

Logs to logs/sync_from_handoff.log.
"""
from __future__ import annotations

import datetime as _dt
import pathlib
import shutil
import subprocess
import sys

LIVE = pathlib.Path(__file__).resolve().parent.parent
HANDOFF = pathlib.Path(r"C:\Users\Aviral Garg\Downloads\vahdam-pnl-handoff")
SRC = HANDOFF / "data" / "pnl_daily_REFERENCE.json"
DST = LIVE / "data" / "pnl_daily.json"
LOG_DIR = LIVE / "logs"; LOG_DIR.mkdir(exist_ok=True)
LOG = LOG_DIR / "sync_from_handoff.log"


def log(msg: str) -> None:
    line = f"[{_dt.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {msg}"
    print(line)
    with LOG.open("a", encoding="utf-8") as fh:
        fh.write(line + "\n")


def main() -> int:
    if not SRC.exists():
        log(f"FAIL handoff file missing: {SRC}")
        return 1
    mtime = _dt.datetime.fromtimestamp(SRC.stat().st_mtime)
    today = _dt.date.today()
    if mtime.date() < today:
        log(f"SKIP Handoff stale, skipping deploy "
            f"(handoff mtime={mtime.isoformat()}, today={today.isoformat()})")
        return 0

    log(f"Handoff fresh (mtime={mtime.isoformat()}); copying to live")
    shutil.copy2(SRC, DST)
    size = DST.stat().st_size
    log(f"  copied -> {DST} ({size:,} bytes)")

    # FIX 4: Rebuild US monthly_history from raw_metric_keyed snapshot. The
    # handoff JSON ships with US.overall = {} and the metric-keyed structure
    # under overall_raw_metric_keyed. Transform to month-keyed schema (same as
    # UK) so the dashboard Monthly CM History table renders US rows.
    log("Rebuilding US monthly_history...")
    rc_us = subprocess.run(
        [sys.executable, str(LIVE / "scripts" / "rebuild_us_monthly.py")],
        cwd=LIVE, capture_output=True, text=True,
    )
    if rc_us.returncode != 0:
        log(f"FAIL rebuild_us_monthly rc={rc_us.returncode}\nSTDERR: {rc_us.stderr[:300]}")
        return 5
    log("  rebuild_us_monthly OK")

    # Rebuild
    log("Rebuilding dashboard...")
    rc = subprocess.run(
        [sys.executable, str(LIVE / "scripts" / "build_dashboard.py")],
        cwd=LIVE, capture_output=True, text=True,
    )
    if rc.returncode != 0:
        log(f"FAIL build_dashboard rc={rc.returncode}\nSTDERR: {rc.stderr[:500]}")
        return 2
    log(f"  build_dashboard OK  ({rc.stdout.strip().splitlines()[-1] if rc.stdout.strip() else ''})")

    # Git commit + push
    def gr(args):
        return subprocess.run(["git"] + args, cwd=LIVE, capture_output=True, text=True)
    gr(["add", "data/pnl_daily.json", "public/index.html"])
    diff = gr(["diff", "--cached", "--quiet"])
    if diff.returncode == 0:
        log("No staged changes -- nothing to commit (data already up to date)")
        return 0
    msg = f"data: daily refresh from Cowork handoff {today.isoformat()}"
    c = gr(["commit", "-m", msg])
    if c.returncode != 0:
        log(f"FAIL git commit: {c.stderr[:300]}")
        return 3
    log(f"  committed: {msg}")
    # Resolve the remote name dynamically (this repo uses "vahdam-pnl-live-",
    # not the conventional "origin").
    remotes = subprocess.run(["git", "remote"], cwd=LIVE, capture_output=True, text=True).stdout.split()
    remote = "origin" if "origin" in remotes else (remotes[0] if remotes else "origin")
    p = gr(["push", remote, "main"])
    if p.returncode != 0:
        log(f"FAIL git push: {p.stderr[:300]}")
        return 4
    log("  pushed to origin/main -- Vercel will auto-deploy")
    return 0


if __name__ == "__main__":
    sys.exit(main())
