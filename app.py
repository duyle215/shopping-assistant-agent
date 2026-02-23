"""
Flask Web UI cho Shopping Assistant.
Chay bang lenh: python app.py
Truy cap:       http://localhost:5000
"""

import json
import os

from dotenv import load_dotenv
from flask import Flask, jsonify, render_template, request

load_dotenv()

app = Flask(__name__)

# Khoi tao agent mot lan duy nhat khi server start
from agent_core import ShoppingAgent

agent = ShoppingAgent()


# ------------------------------------------------------------------
# PAGES
# ------------------------------------------------------------------
@app.route("/")
def index():
    return render_template("index.html")


@app.route("/products-page")
def products_page():
    return render_template("index.html", page="products")


# ------------------------------------------------------------------
# API ENDPOINTS (goi tu JavaScript)
# ------------------------------------------------------------------
@app.post("/api/chat")
def api_chat():
    data = request.get_json(force=True)
    message = (data.get("message") or "").strip()
    if not message:
        return jsonify({"error": "Tin nhan trong."}), 400

    try:
        result = agent.run(message)
        return jsonify(
            {
                "intent": result.intent,
                "answer_markdown": result.answer_markdown,
                "tools_called": result.tools_called,
                "warning": result.warning,
            }
        )
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.get("/api/products")
def api_products():
    try:
        from sqlalchemy import create_engine, text

        pg_url = (
            f"postgresql+psycopg2://{os.getenv('POSTGRES_USER')}:{os.getenv('POSTGRES_PASSWORD')}"
            f"@{os.getenv('POSTGRES_HOST')}:{os.getenv('POSTGRES_PORT')}/{os.getenv('POSTGRES_DB')}"
        )
        engine = create_engine(pg_url, echo=False)
        with engine.connect() as conn:
            rows = conn.execute(
                text(
                    "SELECT id, name, brand, price, specs, description FROM products ORDER BY id"
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
                    "specs": (
                        json.loads(r.specs) if isinstance(r.specs, str) else r.specs
                    ),
                    "description": r.description,
                }
            )
        return jsonify({"total": len(products), "products": products})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.get("/api/health")
def api_health():
    results = {}

    # Postgres
    try:
        from sqlalchemy import create_engine, text

        pg_url = (
            f"postgresql+psycopg2://{os.getenv('POSTGRES_USER')}:{os.getenv('POSTGRES_PASSWORD')}"
            f"@{os.getenv('POSTGRES_HOST')}:{os.getenv('POSTGRES_PORT')}/{os.getenv('POSTGRES_DB')}"
        )
        with create_engine(pg_url).connect() as c:
            c.execute(text("SELECT 1"))
        results["postgres"] = "OK"
    except Exception as e:
        results["postgres"] = f"FAIL: {e}"

    # Qdrant
    try:
        from qdrant_client import QdrantClient

        QdrantClient(path=os.getenv("QDRANT_PATH", "./qdrant_data")).get_collections()
        results["qdrant"] = "OK"
    except Exception as e:
        results["qdrant"] = f"FAIL: {e}"

    # Ollama
    try:
        import requests

        resp = requests.get(
            f"{os.getenv('OLLAMA_URL', 'http://localhost:11434')}/api/tags", timeout=3
        )
        resp.raise_for_status()
        results["ollama"] = "OK"
    except Exception as e:
        results["ollama"] = f"FAIL: {e}"

    status = "OK" if all(v == "OK" for v in results.values()) else "DEGRADED"
    return jsonify({"status": status, **results})


# ------------------------------------------------------------------
# RUN
# ------------------------------------------------------------------
if __name__ == "__main__":
    print("=" * 50)
    print("  Shopping Assistant  |  Flask Web UI")
    print("  http://localhost:5000")
    print("=" * 50)
    app.run(host="0.0.0.0", port=5000, debug=True, use_reloader=False)
