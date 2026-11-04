"""
Bang cua agent (SQLAlchemy ORM). San pham, don hang, yeu cau ho tro nam o Odoo;
database cua agent chi con traces va checkpoint cua LangGraph (do PostgresSaver tu tao).
"""

from __future__ import annotations

from sqlalchemy import Column, DateTime, Integer, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.engine import Engine
from sqlalchemy.orm import declarative_base

Base = declarative_base()


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


def create_tables(engine: Engine) -> None:
    """Tao bang con thieu (khong xoa du lieu)."""
    Base.metadata.create_all(engine)


def reset_db(engine: Engine) -> None:
    """Xoa va tao lai toan bo bang (dung khi nap lai du lieu mau)."""
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
