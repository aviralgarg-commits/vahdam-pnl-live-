"""
test_auth.py -- STEP 6 verification.

Launches each region's cloned Chrome profile via Playwright's
launch_persistent_context, navigates to {region}/homepage, and confirms
the Seller Center loaded with VAHDAM marker (or seller domain w/ no login UI).

Expected output:
  uk: AUTHENTICATED
  us: AUTHENTICATED

If either says NOT_LOGGED_IN, the clone is stale -- re-clone the source
profile after re-logging in there.

Run: ./venv/Scripts/python.exe scripts/test_auth.py
"""
from __future__ import annotations

import json
import pathlib
import sys
import time
from datetime import datetime as _dt

ROOT = pathlib.Path(__file__).resolve().parent.parent
CFG = ROOT / "config" / "chrome_profiles.json"
LOG = ROOT / "logs" / "test_auth.log"
LOG.parent.mkdir(exist_ok=True)

HOMEPAGE = {
    "uk": "https://seller-uk.tiktok.com/homepage",
    "us": "https://seller-us.tiktok.com/homepage",
}
AUTH_MARKERS = ["VAHDAM", "Vahdam", "vahdam", "Seller Center", "Order management"]


def log(msg: str) -> None:
    line = f"[{_dt.now().strftime('%Y-%m-%d %H:%M:%S')}] {msg}"
    print(line)
    with LOG.open("a", encoding="utf-8") as fh:
        fh.write(line + "\n")


def check_region(region: str) -> bool:
    cfg = json.loads(CFG.read_text(encoding="utf-8"))[region]
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        log("ERROR: playwright not installed.")
        return False
    chrome_exe = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
    log(f"{region}: launching REAL chrome.exe with user_data_dir={cfg['user_data_dir']} "
        f"profile_directory={cfg['profile_directory']} (channel=chrome for ABE compat)")
    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(
            user_data_dir=cfg["user_data_dir"],
            executable_path=chrome_exe,
            headless=False,
            args=[
                f"--profile-directory={cfg['profile_directory']}",
                "--disable-blink-features=AutomationControlled",
                "--no-first-run",
                "--no-default-browser-check",
            ],
            viewport=None,
        )
        try:
            page = ctx.pages[0] if ctx.pages else ctx.new_page()
            page.goto(HOMEPAGE[region], wait_until="domcontentloaded", timeout=45_000)
            try:
                page.wait_for_load_state("networkidle", timeout=15_000)
            except Exception:
                pass
            url = page.url or ""
            body = ""
            for _ in range(8):  # up to 16s post-load
                try:
                    body = page.inner_text("body", timeout=2000)
                except Exception:
                    body = ""
                if any(m in body for m in AUTH_MARKERS):
                    break
                time.sleep(2)
            has_marker = any(m in body for m in AUTH_MARKERS)
            on_login = "login" in url.lower() or "passport" in url.lower()
            log(f"{region}: final URL = {url[:120]}")
            log(f"{region}: body length = {len(body)} chars, marker present = {has_marker}, on login page = {on_login}")
            authed = has_marker and not on_login
            if not authed:
                snippet = body[:300].replace("\n", " | ")
                log(f"{region}: body snippet -> {snippet}")
            return authed
        finally:
            try:
                ctx.close()
            except Exception:
                pass


def main() -> int:
    results = {}
    for region in ("uk", "us"):
        log(f"=== Region {region.upper()} ===")
        try:
            authed = check_region(region)
        except Exception as e:
            log(f"{region}: EXCEPTION {e}")
            authed = False
        results[region] = authed
        print(f"{region}: {'AUTHENTICATED' if authed else 'NOT_LOGGED_IN -- fix profile copy'}")

    print()
    print("=" * 50)
    for r, ok in results.items():
        print(f"  {r}: {'AUTHENTICATED' if ok else 'NOT_LOGGED_IN'}")
    print("=" * 50)
    return 0 if all(results.values()) else 1


if __name__ == "__main__":
    sys.exit(main())
