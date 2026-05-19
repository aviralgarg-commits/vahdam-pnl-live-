"""
_cdp.py — shared helper for attaching Playwright to the user's REAL Chrome
via Chrome DevTools Protocol on localhost:9222.

Why CDP attach (NOT launch_persistent_context):
  - Playwright's launch_persistent_context with a tmp dir or storage_state
    LOSES TikTok's service-worker auth and loops on login forever (we tried).
  - connect_over_cdp attaches to the user's real, already-logged-in Chrome.
    Cookies + service workers + Google SSO are all intact.
  - The user runs scripts/launch_chrome_debug.bat once per boot (or pins to
    shell:startup) to keep Chrome listening on :9222.

Usage (sync):

    from _cdp import attach, detach, CdpUnavailable
    try:
        pw, browser, context = attach()
    except CdpUnavailable as e:
        log(f"CDP_UNAVAILABLE -- {e}")
        return

    page = context.new_page()
    try:
        page.goto("https://seller-uk.tiktok.com/homepage")
        # … scrape …
    finally:
        page.close()
        detach(pw, browser)   # disconnects; does NOT close real Chrome
"""
from __future__ import annotations

import json
import urllib.request


CDP_URL = "http://localhost:9222"


class CdpUnavailable(RuntimeError):
    pass


def is_chrome_running() -> bool:
    try:
        with urllib.request.urlopen(f"{CDP_URL}/json/version", timeout=2) as r:
            json.loads(r.read())
        return True
    except Exception:
        return False


def attach():
    if not is_chrome_running():
        raise CdpUnavailable(
            f"No Chrome listening at {CDP_URL}. "
            f"Run scripts\\launch_chrome_debug.bat first."
        )
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as e:
        raise CdpUnavailable(f"playwright not installed: {e}")

    pw = sync_playwright().start()
    try:
        browser = pw.chromium.connect_over_cdp(CDP_URL)
    except Exception as e:
        pw.stop()
        raise CdpUnavailable(f"connect_over_cdp failed: {e}")

    if not browser.contexts:
        browser.close()
        pw.stop()
        raise CdpUnavailable("Chrome reported zero contexts via CDP")

    context = browser.contexts[0]
    return pw, browser, context


def detach(pw, browser) -> None:
    """Disconnects from CDP without closing the user's real Chrome."""
    try:
        browser.close()
    except Exception:
        pass
    try:
        pw.stop()
    except Exception:
        pass


# Defensive recursive text walker (used by scrapers when innerText misses
# shadow DOM / extension-injected content). Pass as JS to page.evaluate().
SHADOW_TEXT_JS = r"""
() => {
  let txt = '';
  function walk(el){
    if(!el) return;
    if(el.nodeType === 3){ txt += el.textContent + ' '; }
    if(el.shadowRoot){ walk(el.shadowRoot); }
    for(const c of (el.childNodes || [])){ walk(c); }
  }
  walk(document.body);
  return txt;
}
"""


def shared_scrape_setup(region: str, url: str, log_fn):
    """Boilerplate for a scrape:
      1. Attach via CDP
      2. Open new page
      3. Pre-flight auth check on /homepage (VAHDAM marker within 10s)
      4. Return (pw, browser, ctx, page) — caller navigates to its target URL

    Returns None on failure (caller should `return` without continuing).
    """
    try:
        pw, browser, ctx = attach()
    except CdpUnavailable as e:
        log_fn(f"CDP_UNAVAILABLE -- {region} skipped: {e}")
        return None
    page = ctx.new_page()
    homepage = f"https://seller-{region.lower()}.tiktok.com/homepage"
    try:
        page.goto(homepage, wait_until="domcontentloaded", timeout=30_000)
    except Exception as e:
        log_fn(f"AUTH_LOST_{region}_homepage_nav_failed: {e}")
        try: page.close()
        except Exception: pass
        detach(pw, browser)
        return None

    import time
    deadline = time.time() + 10
    while time.time() < deadline:
        try:
            body = page.inner_text("body", timeout=2000)
            if "VAHDAM" in body or "Vahdam" in body:
                return (pw, browser, ctx, page)
        except Exception:
            pass
        time.sleep(1)
    log_fn(f"AUTH_LOST_{region}_at_{page.url}_no_VAHDAM_marker")
    try: page.close()
    except Exception: pass
    detach(pw, browser)
    return None
