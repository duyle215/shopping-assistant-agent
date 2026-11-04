"""
Database tables (SQLAlchemy ORM). Dung chung cho app, scripts va tests.
"""

from __future__ import annotations

from sqlalchemy import Column, Integer, Numeric, String, Text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import declarative_base

Base = declarative_base()


class Product(Base):
    __tablename__ = "products"
    id = Column(Integer, primary_key=True)
    name = Column(String(255), nullable=False)
    brand = Column(String(100), nullable=False)
    price = Column(Numeric(15, 0), nullable=False)
    stock = Column(Integer, nullable=False, default=0)
    specs = Column(Text, nullable=True)
    description = Column(Text, nullable=True)


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


def reset_db(engine: Engine) -> None:
    """Xoa va tao lai toan bo bang (dung khi nap lai du lieu mau)."""
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
