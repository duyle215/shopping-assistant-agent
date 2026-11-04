"""
Product service - truy van san pham tu Postgres.
"""

from __future__ import annotations

from typing import Optional

from sqlalchemy import bindparam, text

from app.agent.schemas import ProductMetadata
from app.db import get_engine

PRODUCT_COLUMNS = (
    "id, name, brand, model, price, stock, chipset, ram_gb, storage_gb, screen_inch, "
    "refresh_rate_hz, battery_mah, charging_w, main_camera_mp, weight_g, os, release_year"
)


def _to_model(row) -> ProductMetadata:
    data = dict(row._mapping)
    data["price"] = int(data["price"])
    return ProductMetadata(**data)


def get_product_details(product_id: int) -> Optional[ProductMetadata]:
    """Lay thong so ky thuat chi tiet mot san pham."""
    with get_engine().connect() as conn:
        row = conn.execute(
            text(f"SELECT {PRODUCT_COLUMNS} FROM products WHERE id = :pid"),
            {"pid": product_id},
        ).fetchone()
    return _to_model(row) if row else None


def get_products(product_ids: list[int]) -> list[ProductMetadata]:
    """Lay nhieu san pham, giu dung thu tu product_ids."""
    if not product_ids:
        return []
    stmt = text(f"SELECT {PRODUCT_COLUMNS} FROM products WHERE id IN :ids").bindparams(
        bindparam("ids", expanding=True)
    )
    with get_engine().connect() as conn:
        rows = {r.id: _to_model(r) for r in conn.execute(stmt, {"ids": list(product_ids)})}
    return [rows[i] for i in product_ids if i in rows]


def list_products() -> list[ProductMetadata]:
    with get_engine().connect() as conn:
        rows = conn.execute(text(f"SELECT {PRODUCT_COLUMNS} FROM products ORDER BY id"))
        return [_to_model(r) for r in rows]
