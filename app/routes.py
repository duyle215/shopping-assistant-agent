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


# ------------------------------------------------------------------
# API ENDPOINTS
# ------------------------------------------------------------------
@api.post("/api/chat")
def api_chat():
    """Mot luot chat, tra JSON. Neu can xac nhan don hang: pending_confirmation != null."""
    data = request.get_json(force=True)
    message = (data.get("message") or "").strip()
    session_id = data.get("session_id") or None
    if not message:
        return jsonify({"error": "Tin nhan trong."}), 400

    try:
        result = _get_agent().run(message, session_id=session_id)
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
    return _sse(_get_agent().stream(message, session_id=session_id))


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


@api.get("/api/stock")
def api_stock():
    """Xem ton kho toan bo san pham."""
    try:
        from app.services.inventory import get_all_stock

        stock_list = get_all_stock()
        return jsonify({"total": len(stock_list), "stock": stock_list})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@api.route("/api/stock", methods=["PATCH"])
def api_stock_update():
    """Cap nhat so luong ton kho (nhan vien kho/demo)."""
    data = request.get_json(force=True)
    product_id = data.get("product_id")
    new_stock = data.get("stock")

    if product_id is None or new_stock is None:
        return jsonify({"error": "Can truyen product_id va stock."}), 400

    try:
        product_id = int(product_id)
        new_stock = int(new_stock)
    except (ValueError, TypeError):
        return jsonify({"error": "product_id va stock phai la so nguyen."}), 400

    try:
        from app.services.inventory import update_stock

        result = update_stock(product_id, new_stock)
        if "error" in result:
            return jsonify(result), 400
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@api.get("/api/orders")
def api_orders():
    """Xem danh sach don hang (cho nhan vien/admin)."""
    try:
        from app.services.inventory import get_pending_orders

        orders = get_pending_orders()
        return jsonify({"total": len(orders), "orders": orders})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@api.get("/api/support-requests")
def api_support_requests():
    """Xem danh sach yeu cau ho tro (cho nhan vien/admin)."""
    try:
        from app.services.support import get_pending_support_requests

        requests_list = get_pending_support_requests()
        return jsonify({"total": len(requests_list), "requests": requests_list})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


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

    status = "OK" if all(v == "OK" for v in results.values()) else "DEGRADED"
    return jsonify({"status": status, **results})
