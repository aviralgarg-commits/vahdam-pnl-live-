"""
server.py — FastAPI server for Vahdam P&L Live dashboard.

Endpoints:
  GET  /           → serve public/index.html
  GET  /api/health → last refresh time + data window
  POST /api/refresh → trigger full refresh pipeline
  POST /api/ask    → ask a free-form question about the data (Claude-backed)
"""

import json
import os
import pathlib
import subprocess
import sys
import time
from datetime import datetime

from fastapi import FastAPI, BackgroundTasks, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv

load_dotenv(pathlib.Path(__file__).resolve().parent / ".env")

ROOT = pathlib.Path(__file__).resolve().parent
PUBLIC = ROOT / "public"
DATA = ROOT / "data" / "pnl_daily.json"
SCRIPTS = ROOT / "scripts"
PYTHON = ROOT / "venv" / "Scripts" / "python.exe"

app = FastAPI(title="Vahdam P&L Live")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

# Rate-limit state for /api/refresh
_last_refresh_at: float = 0.0
_refresh_running: bool = False
REFRESH_COOLDOWN_SEC = 300  # 5 minutes


@app.get("/", response_class=HTMLResponse)
async def index():
    html_path = PUBLIC / "index.html"
    if not html_path.exists():
        return HTMLResponse("<h1>Dashboard not built yet. POST /api/refresh to build.</h1>", status_code=503)
    return HTMLResponse(html_path.read_text(encoding="utf-8"))


@app.get("/api/health")
async def health():
    data_age_sec = None
    window = {}
    if DATA.exists():
        try:
            data = json.loads(DATA.read_text(encoding="utf-8"))
            window = {
                "window_start": data.get("window_start"),
                "window_end": data.get("window_end"),
                "pulled_at": data.get("pulled_at"),
                "orders_count": len(data.get("orders_daily", [])),
                "aff_count": len(data.get("aff_daily", [])),
            }
            data_age_sec = int(time.time() - DATA.stat().st_mtime)
        except Exception:
            pass

    return {
        "status": "ok",
        "last_refresh_at": datetime.fromtimestamp(_last_refresh_at).isoformat() if _last_refresh_at else None,
        "refresh_running": _refresh_running,
        "data_age_seconds": data_age_sec,
        "data": window,
    }


def _do_refresh():
    global _last_refresh_at, _refresh_running
    _refresh_running = True
    try:
        result = subprocess.run(
            [str(PYTHON), str(SCRIPTS / "refresh_daily.py")],
            capture_output=True, text=True, cwd=str(ROOT), timeout=600
        )
        _last_refresh_at = time.time()
        if result.returncode != 0:
            print("Refresh stderr:", result.stderr[-2000:] if result.stderr else "")
        else:
            print("Refresh stdout (last 500):", result.stdout[-500:] if result.stdout else "")
    except subprocess.TimeoutExpired:
        print("Refresh timed out after 600s")
    except Exception as e:
        print(f"Refresh error: {e}")
    finally:
        _refresh_running = False


@app.post("/api/refresh")
async def refresh(background_tasks: BackgroundTasks):
    global _refresh_running
    now = time.time()

    if _refresh_running:
        return JSONResponse({"status": "already_running"}, status_code=202)

    if now - _last_refresh_at < REFRESH_COOLDOWN_SEC:
        wait = int(REFRESH_COOLDOWN_SEC - (now - _last_refresh_at))
        raise HTTPException(status_code=429, detail=f"Rate limited. Try again in {wait}s.")

    background_tasks.add_task(_do_refresh)
    return {"status": "started", "message": "Refresh started in background. Check /api/health."}


# Static files (CSS, JS assets if any)
if PUBLIC.exists():
    app.mount("/static", StaticFiles(directory=str(PUBLIC)), name="static")


# ── Ask a question (Claude-backed) ─────────────────────────────────────────────
ASK_COOLDOWN_SEC = 3
_last_ask_at: dict[str, float] = {}  # ip -> timestamp


def _build_data_context() -> str:
    """Build a compact, model-friendly summary of pnl_daily.json for grounding."""
    if not DATA.exists():
        return "(no data available)"
    d = json.loads(DATA.read_text(encoding="utf-8-sig"))

    # Aggregate orders_daily by (region, sku, variation) -> totals across window
    orders_by_key: dict[tuple, dict] = {}
    for r in d.get("orders_daily", []):
        if r.get("is_free_gift"):
            continue
        key = (r.get("region"), r.get("sku"), r.get("variation"))
        b = orders_by_key.setdefault(key, {"net_orders": 0, "net_qty": 0, "net_sales": 0.0,
                                            "cancelled_orders": 0, "sample_orders": 0,
                                            "refund": 0.0, "currency": r.get("currency", "")})
        b["net_orders"] += r.get("net_orders", 0) or 0
        b["net_qty"] += r.get("net_qty", 0) or 0
        b["net_sales"] += r.get("net_sales", 0) or 0
        b["cancelled_orders"] += r.get("cancelled_orders", 0) or 0
        b["sample_orders"] += r.get("sample_orders", 0) or 0
        b["refund"] += r.get("refund", 0) or 0

    # Ad spend totals
    ad30 = d.get("ad_spend_30d", {})

    # Smart promo
    sp = d.get("smart_promo_monthly", [])

    # Affiliate totals by region
    aff_uk = sum(r.get("aff_commission", 0) for r in d.get("aff_daily", []) if r.get("region") == "UK")
    aff_us = sum(r.get("aff_commission", 0) for r in d.get("aff_daily", []) if r.get("region") == "US")

    lines = [
        f"DATA WINDOW: {d.get('window_start')} -> {d.get('window_end')} ({d.get('window_days')} days)",
        f"LAST REFRESH: {d.get('pulled_at')}",
        f"WINDOW END (UK): {d.get('window_end_uk')}  WINDOW END (US): {d.get('window_end_us')}",
        "",
        "=== ORDERS by (region, SKU, variation) ===",
        "region | sku | variation | net_orders | net_qty | net_sales | cancelled | samples | refunds | ccy",
    ]
    for (region, sku, variation), b in sorted(orders_by_key.items()):
        lines.append(
            f"{region} | {sku} | {variation} | {b['net_orders']} | {b['net_qty']:.0f} | "
            f"{b['net_sales']:.0f} | {b['cancelled_orders']} | {b['sample_orders']} | "
            f"{b['refund']:.0f} | {b['currency']}"
        )

    lines += [
        "",
        "=== AFFILIATE COMMISSION (window totals) ===",
        f"UK: GBP {aff_uk:,.0f}",
        f"US: USD {aff_us:,.0f}",
        "",
        "=== AD SPEND L30 (Shop Ads, scraped from Seller Center) ===",
        f"UK total: GBP {ad30.get('UK', {}).get('total_cost', 0):,.0f}",
        f"US total: USD {ad30.get('US', {}).get('total_cost', 0):,.0f}",
        f"UK window: {ad30.get('window_start')} -> {ad30.get('window_end')}",
        "",
        "UK Product GMV Max campaigns (top 10):",
    ]
    for c in (ad30.get("UK", {}).get("product_gmv_max", [])[:10]):
        lines.append(f"  GBP {c.get('cost', 0):,.0f}  {c.get('campaign', '')}  [{c.get('sku', '-')}]")
    lines.append("UK LIVE GMV Max campaigns:")
    for c in (ad30.get("UK", {}).get("live_gmv_max", [])[:8]):
        lines.append(f"  GBP {c.get('cost', 0):,.0f}  {c.get('campaign', '')}")
    lines.append("US Product GMV Max campaigns (top 10):")
    for c in (ad30.get("US", {}).get("product_gmv_max", [])[:10]):
        lines.append(f"  USD {c.get('cost', 0):,.0f}  {c.get('campaign', '')}  [{c.get('sku', '-')}]")

    lines += ["", "=== SMART PROMOTION (monthly) ==="]
    for e in sp[:6]:
        lines.append(f"  {e}")

    lines += [
        "",
        "=== UK COSTS PER PACK (CM1 inputs) ===",
        json.dumps(d.get("costs_uk", {}).get("costs_per_pack", {}), indent=0)[:2000],
        "",
        "=== US COSTS PER PACK (CM1 inputs) ===",
        json.dumps(d.get("costs_us", {}).get("costs_per_pack", {}), indent=0)[:2000],
    ]

    return "\n".join(lines)


SYSTEM_PROMPT = """You are the Vahdam P&L data analyst assistant. You answer questions about TikTok Shop UK + US performance using the data summary provided.

Rules:
- Be concise. Use plain numbers and short sentences.
- Always specify currency (GBP for UK, USD for US) when quoting money.
- Cite the metric source ("from orders_daily", "from ad spend", "from affiliate commission").
- If the question can't be answered from the data shown, say so explicitly and suggest what would be needed.
- For CM1/CM2 questions, walk through the build-up: Net Sales -> ex-VAT (UK) -> minus unit costs (COGs, TT commission, DSF, etc.) -> CM1, then minus marketing (affiliate, ad spend ×1.20 VAT-incl for UK, smart promo, plus VAT recovery 20/120) -> CM2.
- UK VAT rules: zero-rated supplements (Coffee from Apr 2026, Green Burner, Ashwagandha Caps, Turmeric Curcumin) drop 20% VAT from net sales. Ginger Tea keeps VAT.
- UK per-order shipping = £1.99 from 2026-03-01 onwards.
- Free gifts (Frother, Butterfly Pea Tea) are excluded from totals by default.

If asked something off-topic, briefly redirect to dashboard scope.
"""


@app.post("/api/ask")
async def ask(request: Request):
    # Ask AI feature disabled per product decision. Leaving stub for easy re-enable later.
    raise HTTPException(status_code=404, detail="Ask AI endpoint is disabled.")
    api_key = os.getenv("ANTHROPIC_API_KEY", "").strip()
    if not api_key:
        return JSONResponse(
            {"error": "Ask AI is not configured. Set ANTHROPIC_API_KEY in .env on the server."},
            status_code=503,
        )

    # Simple per-IP cooldown (3s) to avoid runaway calls if shared publicly
    ip = request.client.host if request.client else "unknown"
    now = time.time()
    if now - _last_ask_at.get(ip, 0) < ASK_COOLDOWN_SEC:
        return JSONResponse({"error": "Slow down — try again in a couple seconds."}, status_code=429)
    _last_ask_at[ip] = now

    body = await request.json()
    question = (body.get("question") or "").strip()
    if not question:
        raise HTTPException(status_code=400, detail="question is required")
    if len(question) > 1000:
        raise HTTPException(status_code=400, detail="question too long (max 1000 chars)")

    try:
        import anthropic
        client = anthropic.Anthropic(api_key=api_key)
        ctx = _build_data_context()
        msg = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=800,
            system=SYSTEM_PROMPT,
            messages=[
                {"role": "user", "content": f"<dashboard_data>\n{ctx}\n</dashboard_data>\n\nQuestion: {question}"},
            ],
        )
        answer = "".join(block.text for block in msg.content if hasattr(block, "text"))
        return {"answer": answer, "model": msg.model, "usage": {
            "input_tokens": msg.usage.input_tokens,
            "output_tokens": msg.usage.output_tokens,
        }}
    except Exception as e:
        return JSONResponse({"error": f"LLM call failed: {e}"}, status_code=500)


if __name__ == "__main__":
    import uvicorn

    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("PORT", "8000"))

    print(f"\nVahdam P&L Live server starting on http://{host}:{port}/")
    print(f"POST http://localhost:{port}/api/refresh to rebuild dashboard")
    uvicorn.run("server:app", host=host, port=port, reload=False)
