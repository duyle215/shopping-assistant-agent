"""
Cau hinh tap trung - doc tat ca bien moi truong tu .env mot lan duy nhat.

Moi module trong project import tu day thay vi tu doc os.getenv rieng le.
"""

import os
import sys
from urllib.parse import quote

from dotenv import load_dotenv

load_dotenv()


# ------------------------------------------------------------------
# HELPER
# ------------------------------------------------------------------
def _require(key: str) -> str:
    """Doc bien moi truong bat buoc. Thoat neu thieu."""
    val = os.getenv(key)
    if not val:
        sys.exit(f"[ERROR] Thieu bien '{key}' trong file .env")
    return val


# ------------------------------------------------------------------
# OPENAI / EMBEDDING
# ------------------------------------------------------------------
OPENAI_BASE_URL = _require("OPENAI_BASE_URL")
OPENAI_API_KEY = _require("OPENAI_API_KEY")
EMBED_MODEL = _require("EMBED_MODEL")
EMBED_DIM = int(_require("EMBED_DIM"))
LLM_MODEL = _require("LLM_MODEL")
# Model du phong khi model chinh het quota (vd free tier: moi model co han muc ngay rieng)
LLM_FALLBACK_MODEL = os.getenv("LLM_FALLBACK_MODEL") or None

# Agent Loop co the dung endpoint rieng (fallback ve OpenAI)
AGENT_BASE_URL = os.getenv("AGENT_LOOP_BASE_URL") or OPENAI_BASE_URL
AGENT_API_KEY = os.getenv("AGENT_LOOP_API_KEY") or OPENAI_API_KEY

# ------------------------------------------------------------------
# POSTGRESQL
# ------------------------------------------------------------------
PG_HOST = _require("POSTGRES_HOST")
PG_PORT = _require("POSTGRES_PORT")
PG_DB = _require("POSTGRES_DB")
PG_USER = _require("POSTGRES_USER")
PG_PASSWORD = _require("POSTGRES_PASSWORD")

PG_URL = (
    f"postgresql+psycopg2://{PG_USER}:{PG_PASSWORD}" f"@{PG_HOST}:{PG_PORT}/{PG_DB}"
)
# DSN cho psycopg 3 (LangGraph checkpointer luu trang thai hoi thoai)
PG_DSN = (
    f"postgresql://{quote(PG_USER, safe='')}:{quote(PG_PASSWORD, safe='')}"
    f"@{PG_HOST}:{PG_PORT}/{PG_DB}"
)

# ------------------------------------------------------------------
# QDRANT
# ------------------------------------------------------------------
# Mac dinh chay Qdrant local (luu file trong QDRANT_PATH).
# Set QDRANT_URL (vd http://qdrant:6333) de dung Qdrant server, nhu trong Docker Compose.
QDRANT_URL = os.getenv("QDRANT_URL") or None
QDRANT_PATH = os.getenv("QDRANT_PATH", "./qdrant_data")
QDRANT_COLLECTION = _require("QDRANT_COLLECTION")

# ------------------------------------------------------------------
# ODOO (backend: san pham, ton kho, don hang, yeu cau ho tro)
# ------------------------------------------------------------------
ODOO_URL = os.getenv("ODOO_URL", "http://localhost:8069")
ODOO_DB = os.getenv("ODOO_DB", "odoo")
# API key cua user chatbot; de trong thi doc tu odoo/secrets/<db>.json (do odoo-setup tao)
ODOO_API_KEY = os.getenv("ODOO_API_KEY") or ""
ODOO_ADMIN_API_KEY = os.getenv("ODOO_ADMIN_API_KEY") or ""
ODOO_SECRETS_DIR = os.getenv(
    "ODOO_SECRETS_DIR", os.path.join(os.path.dirname(os.path.dirname(__file__)), "odoo", "secrets")
)
ODOO_TIMEOUT = float(os.getenv("ODOO_TIMEOUT", "30"))

# ------------------------------------------------------------------
# AGENT LOOP
# ------------------------------------------------------------------
MAX_ITERATIONS = 10

# Guardrail bang LLM (lop thu hai sau regex). De trong = tat (tiet kiem quota).
GUARD_MODEL = os.getenv("GUARD_MODEL") or None

# ------------------------------------------------------------------
# FLASK
# ------------------------------------------------------------------
FLASK_HOST = os.getenv("FLASK_HOST", "0.0.0.0")
FLASK_PORT = int(os.getenv("FLASK_PORT", "5000"))
FLASK_DEBUG = os.getenv("FLASK_DEBUG", "false").lower() == "true"
