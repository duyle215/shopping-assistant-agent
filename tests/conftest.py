"""
Test fixtures. Tests chay tren mot database rieng (mac dinh: shopping_assistant_test)
de khong dung vao du lieu demo. Can PostgreSQL dang chay; neu khong co thi skip.
"""

from __future__ import annotations

import os

import pytest
from dotenv import load_dotenv

load_dotenv()

# Tests khong goi LLM: cho gia tri gia de app.config khong thoat vi thieu bien.
for key, value in {
    "OPENAI_BASE_URL": "http://localhost/unused",
    "OPENAI_API_KEY": "unused",
    "LLM_MODEL": "unused",
    "EMBED_MODEL": "unused",
    "EMBED_DIM": "8",
    "POSTGRES_HOST": "localhost",
    "POSTGRES_PORT": "5432",
    "POSTGRES_USER": "postgres",
    "POSTGRES_PASSWORD": "postgres",
    "QDRANT_COLLECTION": "test_products",
}.items():
    os.environ.setdefault(key, value)

TEST_DB = os.getenv("TEST_POSTGRES_DB", "shopping_assistant_test")
os.environ["POSTGRES_DB"] = TEST_DB


def _ensure_database() -> None:
    import psycopg2

    conn = psycopg2.connect(
        host=os.environ["POSTGRES_HOST"],
        port=int(os.environ["POSTGRES_PORT"]),
        user=os.environ["POSTGRES_USER"],
        password=os.environ["POSTGRES_PASSWORD"],
        dbname="postgres",
        connect_timeout=3,
    )
    conn.autocommit = True
    with conn.cursor() as cur:
        cur.execute("SELECT 1 FROM pg_database WHERE datname = %s", (TEST_DB,))
        if not cur.fetchone():
            cur.execute(f'CREATE DATABASE "{TEST_DB}"')
    conn.close()


@pytest.fixture(scope="session")
def engine():
    try:
        _ensure_database()
    except Exception as exc:  # pragma: no cover - depends on the machine
        pytest.skip(f"PostgreSQL khong san sang: {exc}")

    from app.db import get_engine

    return get_engine()


@pytest.fixture()
def db(engine):
    """Database trong, tao lai bang truoc moi test."""
    from app.models import reset_db

    reset_db(engine)
    return engine
