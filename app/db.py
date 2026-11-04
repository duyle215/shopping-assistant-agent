"""
Shared clients - mot engine PostgreSQL (co connection pool) va mot Qdrant client
cho ca process, thay vi tao moi o moi lan goi tool.
"""

from __future__ import annotations

from functools import lru_cache

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine

from app.config import PG_URL, QDRANT_PATH, QDRANT_URL


@lru_cache(maxsize=1)
def get_engine() -> Engine:
    """Engine dung chung. pool_pre_ping bo qua ket noi chet sau khi Postgres restart."""
    return create_engine(
        PG_URL,
        pool_size=5,
        max_overflow=10,
        pool_pre_ping=True,
    )


@lru_cache(maxsize=1)
def get_qdrant():
    """Qdrant client dung chung: server neu co QDRANT_URL, nguoc lai la local file."""
    from qdrant_client import QdrantClient

    if QDRANT_URL:
        return QdrantClient(url=QDRANT_URL)
    return QdrantClient(path=QDRANT_PATH)
