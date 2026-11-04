"""
Test fixtures. Tests chay tren database rieng de khong dung vao du lieu demo:
  - PostgreSQL cua agent: shopping_assistant_test (traces); khong co thi skip.
  - Odoo: database odoo_test (tao bang `docker compose run --rm odoo-setup odoo_test`,
    Odoo chay voi ODOO_DB_FILTER=^odoo); khong co thi cac test dung Odoo bi skip.
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

TEST_ODOO_DB = os.getenv("TEST_ODOO_DB", "odoo_test")
os.environ["ODOO_DB"] = TEST_ODOO_DB
# Key trong .env la cua database demo; tests doc key tu odoo/secrets/odoo_test.json
os.environ.pop("ODOO_API_KEY", None)
os.environ.pop("ODOO_ADMIN_API_KEY", None)


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


# ------------------------------------------------------------------
# ODOO
# ------------------------------------------------------------------
@pytest.fixture(scope="session")
def odoo_admin():
    from app.odoo import OdooError, get_odoo

    try:
        client = get_odoo(admin=True)
        client.call("res.users", "context_get")
    except OdooError as exc:  # pragma: no cover - depends on the machine
        pytest.skip(f"Odoo test database khong san sang: {exc}")
    return client


@pytest.fixture()
def odoo(odoo_admin):
    """Odoo test sach: an het dien thoai cu, huy don va xoa yeu cau ho tro cua chatbot."""
    old = odoo_admin.search("product.template", [("is_phone", "=", True)])
    if old:
        odoo_admin.write("product.template", old, {"active": False})
    orders = odoo_admin.search("sale.order", [("chat_session_id", "!=", False), ("state", "!=", "cancel")])
    if orders:
        odoo_admin.call("sale.order", "action_cancel", ids=orders)
    leads = odoo_admin.search("crm.lead", [("chat_session_id", "!=", False)])
    if leads:
        odoo_admin.call("crm.lead", "unlink", ids=leads)
    return odoo_admin


def set_stock(odoo, tmpl_id: int, qty: int) -> None:
    variant = odoo.search("product.product", [("product_tmpl_id", "=", tmpl_id)])[0]
    location = odoo.search_read("stock.warehouse", [], ["lot_stock_id"], limit=1)[0]["lot_stock_id"][0]
    ctx = {"inventory_mode": True}
    quant = odoo.create(
        "stock.quant",
        {"product_id": variant, "location_id": location, "inventory_quantity": qty},
        context=ctx,
    )
    odoo.call("stock.quant", "action_apply_inventory", ids=[quant], context=ctx)


@pytest.fixture()
def add_phone(odoo):
    """Tao mot dien thoai trong Odoo test, tra ve id product.template."""

    def add(name: str, stock: int = 5, price: int = 20_000_000, **specs) -> int:
        vals = {
            "name": name,
            "type": "consu",
            "is_storable": True,
            "sale_ok": True,
            "list_price": price,
            "taxes_id": [(6, 0, [])],
            "is_phone": True,
            "phone_brand": "Apple",
            "phone_model": name,
            "phone_os": "iOS",
            "phone_chipset": "Chip",
            "phone_ram_gb": 8,
            "phone_storage_gb": "128,256",
            "phone_screen_inch": 6.1,
            "phone_refresh_rate_hz": 60,
            "phone_battery_mah": 4000,
            "phone_main_camera_mp": 48,
        }
        vals.update({f"phone_{k}": v for k, v in specs.items()})
        tmpl_id = odoo.create("product.template", vals)
        if stock:
            set_stock(odoo, tmpl_id, stock)
        return tmpl_id

    return add
