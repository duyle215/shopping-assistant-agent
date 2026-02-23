"""
Flask routes - Tat ca API endpoints.
"""

from __future__ import annotations

import json
from flask import Blueprint, jsonify, render_template, request
from sqlalchemy import create_engine, text

from app.config import PG_URL, QDRANT_PATH

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
    data = request.get_json(force=True)
    message = (data.get("message") or "").strip()
    session_id = data.get("session_id") or None
    if not message:
        return jsonify({"error": "Tin nhan trong."}), 400

    try:
        agent = _get_agent()
        result = agent.run(message, session_id=session_id)
        return jsonify(
            {
                "intent": result.intent,
                "answer_markdown": result.answer_markdown,
                "tools_called": result.tools_called,
                "warning": result.warning,
                "session_id": result.session_id,
            }
        )
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@api.post("/api/session/clear")
def api_session_clear():
    data = request.get_json(force=True)
    session_id = data.get("session_id")
    if session_id:
        agent = _get_agent()
        agent.sessions.clear(session_id)
    return jsonify({"status": "ok"})


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


@api.get("/api/products")
def api_products():
    try:
        engine = create_engine(PG_URL, echo=False)
        with engine.connect() as conn:
            rows = conn.execute(
                text(
                    "SELECT id, name, brand, price, stock, specs, description "
                    "FROM products ORDER BY id"
                )
            ).fetchall()

        products = []
        for r in rows:
            products.append(
                {
                    "id": r.id,
                    "name": r.name,
                    "brand": r.brand,
                    "price": float(r.price),
                    "stock": int(r.stock),
                    "specs": (
                        json.loads(r.specs) if isinstance(r.specs, str) else r.specs
                    ),
                    "description": r.description,
                }
            )
        return jsonify({"total": len(products), "products": products})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@api.get("/api/health")
def api_health():
    results = {}

    # Postgres
    try:
        with create_engine(PG_URL).connect() as c:
            c.execute(text("SELECT 1"))
        results["postgres"] = "OK"
    except Exception as e:
        results["postgres"] = f"FAIL: {e}"

    # Qdrant
    try:
        from qdrant_client import QdrantClient

        QdrantClient(path=QDRANT_PATH).get_collections()
        results["qdrant"] = "OK"
    except Exception as e:
        results["qdrant"] = f"FAIL: {e}"

    status = "OK" if all(v == "OK" for v in results.values()) else "DEGRADED"
    return jsonify({"status": status, **results})
