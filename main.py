"""
Phase 4 - FastAPI Application
Entry point: uvicorn main:app --reload

Endpoints:
  GET  /           - thong tin API
  GET  /health     - kiem tra trang thai cac thanh phan
  GET  /products   - danh sach san pham
  GET  /products/{id}  - chi tiet san pham
  POST /chat       - hoi dap voi AI Agent
"""

import os

import requests
from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import create_engine, text

from api.routes.chat import router as chat_router
from api.routes.products import router as products_router
from api.schemas import HealthResponse

load_dotenv()

# ------------------------------------------------------------------
# APP INIT
# ------------------------------------------------------------------
app = FastAPI(
    title="Shopping Assistant API",
    description="AI Agent tu van mua dien thoai - HUFLIT",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

# Cho phep CORS (can thiet khi ket noi Streamlit hoac frontend khac)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ------------------------------------------------------------------
# ROUTERS
# ------------------------------------------------------------------
app.include_router(chat_router)
app.include_router(products_router)


# ------------------------------------------------------------------
# ENDPOINTS
# ------------------------------------------------------------------
@app.get("/", tags=["Root"])
def root():
    return {
        "service": "Shopping Assistant API",
        "version": "1.0.0",
        "docs": "/docs",
    }


@app.get("/health", response_model=HealthResponse, tags=["Health"])
def health_check() -> HealthResponse:
    """Kiem tra ket noi toi Postgres, Qdrant va Ollama."""
    results = {}

    # Postgres
    try:
        pg_url = (
            f"postgresql+psycopg2://"
            f"{os.getenv('POSTGRES_USER')}:{os.getenv('POSTGRES_PASSWORD')}"
            f"@{os.getenv('POSTGRES_HOST')}:{os.getenv('POSTGRES_PORT')}"
            f"/{os.getenv('POSTGRES_DB')}"
        )
        engine = create_engine(pg_url, echo=False)
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        results["postgres"] = "OK"
    except Exception as e:
        results["postgres"] = f"FAIL: {e}"

    # Qdrant
    try:
        from qdrant_client import QdrantClient

        qdrant = QdrantClient(path=os.getenv("QDRANT_PATH", "./qdrant_data"))
        qdrant.get_collections()
        results["qdrant"] = "OK"
    except Exception as e:
        results["qdrant"] = f"FAIL: {e}"

    # Ollama
    try:
        ollama_url = os.getenv("OLLAMA_URL", "http://localhost:11434")
        resp = requests.get(f"{ollama_url}/api/tags", timeout=3)
        resp.raise_for_status()
        results["ollama"] = "OK"
    except Exception as e:
        results["ollama"] = f"FAIL: {e}"

    all_ok = all(v == "OK" for v in results.values())

    return HealthResponse(
        status="OK" if all_ok else "DEGRADED",
        **results,
    )
