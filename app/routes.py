"""
Flask routes - Tat ca API endpoints.
"""

from __future__ import annotations

import json

from flask import Blueprint, Response, jsonify, render_template, request, stream_with_context
from sqlalchemy import text

from app.db import get_engine, get_qdrant

api = Blueprint("api", __name__)

# Agent duoc inject tu __init__.py qua app.config["AGENT"]
_agent = None


def _get_agent():
    """Lazy-load agent tu Flask app config."""
    global _agent
    if _agent is None:
        from flask import current_app

        _agent = current_app.config["AGENT"]
    return _agent


# ------------------------------------------------------------------
# PAGES
# ------------------------------------------------------------------
@api.route("/")
def index():
    return render_template("index.html")


@api.route("/products-page")
def products_page():
    return render_template("index.html", page="products")


@api.route("/embed")
def embed():
    """Chi khung chat, de nhung vao website Odoo (iframe trong addon shopping_assistant_chat)."""
    return render_template("index.html", embed=True)


# ------------------------------------------------------------------
# API ENDPOINTS
# ------------------------------------------------------------------
def _lang(data: dict) -> str:
    """Ngon ngu tra loi: 'vi' (mac dinh) hoac 'en'."""
    return "en" if str(data.get("lang", "")).lower().startswith("en") else "vi"


@api.post("/api/chat")
def api_chat():
    """Mot luot chat, tra JSON. Neu can xac nhan don hang: pending_confirmation != null."""
    data = request.get_json(force=True)
    message = (data.get("message") or "").strip()
    session_id = data.get("session_id") or None
    if not message:
        return jsonify({"error": "Tin nhan trong."}), 400

    try:
        result = _get_agent().run(message, session_id=session_id, lang=_lang(data))
        return jsonify(result.model_dump())
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@api.post("/api/chat/confirm")
def api_chat_confirm():
    """Tra loi cau hoi xac nhan don hang: {"session_id": "...", "approved": true/false}."""
    data = request.get_json(force=True)
    session_id = data.get("session_id")
    if not session_id:
        return jsonify({"error": "Thieu session_id."}), 400
    try:
        result = _get_agent().confirm(session_id, bool(data.get("approved")))
        return jsonify(result.model_dump())
    except Exception as e:
        return jsonify({"error": str(e)}), 500


def _sse(events):
    """Server-Sent Events: moi su kien la mot dong 'data: <json>'."""

    def generate():
        try:
            for event in events:
                yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'error': str(e)}, ensure_ascii=False)}\n\n"

    return Response(
        stream_with_context(generate()),
        mimetype="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@api.post("/api/chat/stream")
def api_chat_stream():
    """Nhu /api/chat nhung stream: token, tool dang chay, confirm, final."""
    data = request.get_json(force=True)
    message = (data.get("message") or "").strip()
    if not message:
        return jsonify({"error": "Tin nhan trong."}), 400
    session_id = data.get("session_id") or _get_agent().new_session_id()
    return _sse(_get_agent().stream(message, session_id=session_id, lang=_lang(data)))


@api.post("/api/chat/confirm/stream")
def api_chat_confirm_stream():
    data = request.get_json(force=True)
    session_id = data.get("session_id")
    if not session_id:
        return jsonify({"error": "Thieu session_id."}), 400
    return _sse(_get_agent().stream_confirm(session_id, bool(data.get("approved"))))


@api.post("/api/session/clear")
def api_session_clear():
    data = request.get_json(force=True)
    session_id = data.get("session_id")
    if session_id:
        _get_agent().clear(session_id)
    return jsonify({"status": "ok"})


@api.get("/api/traces")
def api_traces():
    """Cac buoc gan day (goi LLM, goi tool, tong luot). ?session_id=...&limit=50"""
    from app import tracing

    limit = min(int(request.args.get("limit", 50)), 500)
    return jsonify({"traces": tracing.recent(limit, request.args.get("session_id"))})


@api.get("/api/traces/summary")
def api_traces_summary():
    from app import tracing

    hours = min(int(request.args.get("hours", 24)), 24 * 30)
    return jsonify(tracing.summary(hours))


def _display_specs(p) -> dict[str, str]:
    """Thong so dang chu cho the san pham tren giao dien."""
    storage = " / ".join(f"{x // 1024}TB" if x >= 1024 else f"{x}GB" for x in p.storage_gb)
    battery = f"{p.battery_mah} mAh" + (f", sạc {p.charging_w}W" if p.charging_w else "")
    return {
        "Chip": p.chipset,
        "RAM": f"{p.ram_gb} GB",
        "Bộ nhớ": storage,
        "Màn hình": f'{p.screen_inch}" {p.refresh_rate_hz}Hz',
        "Pin": battery,
        "Camera": f"{p.main_camera_mp} MP",
    }


@api.get("/api/products")
def api_products():
    try:
        from app.services.product import list_products

        products = [
            {**p.model_dump(), "specs": _display_specs(p)} for p in list_products()
        ]
        return jsonify({"total": len(products), "products": products})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@api.get("/api/health")
def api_health():
    results = {}

    # Postgres
    try:
        with get_engine().connect() as c:
            c.execute(text("SELECT 1"))
        results["postgres"] = "OK"
    except Exception as e:
        results["postgres"] = f"FAIL: {e}"

    # Qdrant
    try:
        get_qdrant().get_collections()
        results["qdrant"] = "OK"
    except Exception as e:
        results["qdrant"] = f"FAIL: {e}"

    # Odoo (backend: san pham, ton kho, don hang)
    try:
        from app.odoo import get_odoo

        get_odoo().call("res.users", "context_get")
        results["odoo"] = "OK"
    except Exception as e:
        results["odoo"] = f"FAIL: {e}"

    status = "OK" if all(v == "OK" for v in results.values()) else "DEGRADED"
    return jsonify({"status": status, **results})
