"""
_cdp.py — shared helper for attaching Playwright to the user's REAL Chrome
via Chrome DevTools Protocol on localhost:9222.

Why this exists:
  - Playwright's launch_persistent_context spawns its own Chromium under
    a separate profile. TikTok Seller Center's Google SSO doesn't survive
    cleanly there (service-worker tokens get lost), and the headless
    fingerprint trips anti-bot detection.
  - Claude-in-Chrome MCP can't help — TikTok domains are on its denylist.
  - The fix: launch the user's real Chrome with --remote-debugging-port=9222
    (see scripts/launch_chrome_debug.bat), then attach Playwright to it.
    All cookies/SSO/service-workers are intact because we never created a
    fresh context.

Usage (sync Playwright):

    from _cdp import attach, CdpUnavailable
    try:
        pw, browser, context = attach()
    except CdpUnavailable as e:
        log(f"CDP_UNAVAILABLE -- {e}")
        return ...

    page = context.new_page()
    try:
        page.goto(...)
        ...
    finally:
        page.close()
        browser.close()  # disconnects CDP, does NOT close the real Chrome
        pw.stop()
"""
from __future__ import annotations

import json
import urllib.request


CDP_URL = "http://localhost:9222"


class CdpUnavailable(RuntimeError):
    """Raised when the real Chrome isn't running with --remote-debugging-port=9222."""
    pass


def is_chrome_running() -> bool:
    try:
        with urllib.request.urlopen(f"{CDP_URL}/json/version", timeout=2) as r:
            json.loads(r.read())
        return True
    except Exception:
        return False


def attach():
    """Attach Playwright (sync) to the user's running Chrome.

    Returns (playwright, browser, context). The first context in browser.contexts
    is the user's real profile context — that's where the auth lives.

    Raises CdpUnavailable if Chrome isn't listening on port 9222.
    """
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
        # Shouldn't happen — Chrome always has at least one context. Guard
        # anyway.
        browser.close()
        pw.stop()
        raise CdpUnavailable("Chrome reported zero contexts via CDP")

    context = browser.contexts[0]
    return pw, browser, context


def detach(pw, browser) -> None:
    """Clean teardown — disconnects CDP without closing the real Chrome."""
    try:
        browser.close()
    except Exception:
        pass
    try:
        pw.stop()
    except Exception:
        pass
