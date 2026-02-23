"""
Product service - Truy van chi tiet san pham tu Postgres.
"""

from __future__ import annotations

import json
from typing import Optional

from app.config import PG_URL
from app.agent.schemas import ProductMetadata


def get_product_details(product_id: int) -> Optional[ProductMetadata]:
    """Lay thong so ky thuat chi tiet tu Postgres."""
    from sqlalchemy import create_engine, text

    engine = create_engine(PG_URL, echo=False)
    with engine.connect() as conn:
        row = conn.execute(
            text(
                "SELECT id, name, brand, price, stock, specs, description "
                "FROM products WHERE id = :pid"
            ),
            {"pid": product_id},
        ).fetchone()

    if not row:
        return None

    return ProductMetadata(
        id=row.id,
        name=row.name,
        brand=row.brand,
        price=float(row.price),
        stock=int(row.stock),
        specs=json.loads(row.specs) if isinstance(row.specs, str) else row.specs,
        description=row.description,
    )
