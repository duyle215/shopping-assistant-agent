"""
Database tables (SQLAlchemy ORM). Dung chung cho app, scripts va tests.
"""

from __future__ import annotations

from sqlalchemy import Column, DateTime, Float, Integer, Numeric, String, Text, func, text
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.engine import Engine
from sqlalchemy.orm import declarative_base

Base = declarative_base()


class Product(Base):
    """Moi thong so mot cot co kieu, de loc va so sanh bang SQL."""

    __tablename__ = "products"
    id = Column(Integer, primary_key=True)
    name = Column(String(255), nullable=False)
    brand = Column(String(100), nullable=False, index=True)
    model = Column(String(255), nullable=False)
    price = Column(Numeric(15, 0), nullable=False, index=True)
    stock = Column(Integer, nullable=False, default=0)
    chipset = Column(String(100), nullable=False)
    ram_gb = Column(Integer, nullable=False)
    storage_gb = Column(ARRAY(Integer), nullable=False)
    screen_inch = Column(Float, nullable=False)
    refresh_rate_hz = Column(Integer, nullable=False)
    battery_mah = Column(Integer, nullable=False)
    charging_w = Column(Integer, nullable=True)
    main_camera_mp = Column(Integer, nullable=False)
    weight_g = Column(Integer, nullable=True)
    os = Column(String(20), nullable=False)
    release_year = Column(Integer, nullable=True)
    description = Column(Text, nullable=True)
    source = Column(String(255), nullable=True)


class Order(Base):
    __tablename__ = "orders"
    id = Column(Integer, primary_key=True, autoincrement=True)
    product_id = Column(Integer, nullable=False)
    product_name = Column(String(255), nullable=False)
    quantity = Column(Integer, nullable=False)
    customer_name = Column(String(255), nullable=True)
    customer_phone = Column(String(50), nullable=True)
    status = Column(String(50), nullable=False, default="pending")
    note = Column(Text, nullable=True)
    created_at = Column(String(50), nullable=False)


class SupportRequest(Base):
    __tablename__ = "support_requests"
    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(String(100), nullable=True)
    reason = Column(Text, nullable=False)
    customer_name = Column(String(255), nullable=True)
    customer_phone = Column(String(50), nullable=True)
    status = Column(String(50), nullable=False, default="pending")
    created_at = Column(String(50), nullable=False)


class Trace(Base):
    """Mot buoc trong mot luot chat: goi LLM hoac goi tool (do tre, token)."""

    __tablename__ = "traces"
    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(String(100), nullable=True, index=True)
    turn_id = Column(String(40), nullable=True, index=True)
    kind = Column(String(20), nullable=False)  # llm | tool | turn
    name = Column(String(100), nullable=False)  # ten agent / ten tool
    latency_ms = Column(Integer, nullable=True)
    prompt_tokens = Column(Integer, nullable=True)
    completion_tokens = Column(Integer, nullable=True)
    ok = Column(Integer, nullable=False, default=1)
    detail = Column(JSONB, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)


def ensure_extensions(engine: Engine) -> None:
    """pg_trgm cho tim theo tu khoa (hybrid search). Bo qua neu khong co quyen."""
    try:
        with engine.begin() as conn:
            conn.execute(text("CREATE EXTENSION IF NOT EXISTS pg_trgm"))
    except Exception:
        pass


def create_tables(engine: Engine) -> None:
    """Tao bang con thieu (khong xoa du lieu)."""
    ensure_extensions(engine)
    Base.metadata.create_all(engine)


def reset_db(engine: Engine) -> None:
    """Xoa va tao lai toan bo bang (dung khi nap lai du lieu mau)."""
    ensure_extensions(engine)
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
