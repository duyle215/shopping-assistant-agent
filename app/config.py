"""
Cau hinh tap trung - doc tat ca bien moi truong tu .env mot lan duy nhat.

Moi module trong project import tu day thay vi tu doc os.getenv rieng le.
"""

import os
import sys

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

# ------------------------------------------------------------------
# QDRANT
# ------------------------------------------------------------------
QDRANT_PATH = _require("QDRANT_PATH")
QDRANT_COLLECTION = _require("QDRANT_COLLECTION")

# ------------------------------------------------------------------
# AGENT LOOP
# ------------------------------------------------------------------
MAX_ITERATIONS = 10

# ------------------------------------------------------------------
# FLASK
# ------------------------------------------------------------------
FLASK_HOST = os.getenv("FLASK_HOST", "0.0.0.0")
FLASK_PORT = int(os.getenv("FLASK_PORT", "5000"))
FLASK_DEBUG = os.getenv("FLASK_DEBUG", "true").lower() == "true"
