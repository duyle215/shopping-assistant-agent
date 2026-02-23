"""
GET /products        - lay danh sach tat ca san pham
GET /products/{id}   - lay chi tiet mot san pham
"""

import json

from fastapi import APIRouter, HTTPException
from sqlalchemy import create_engine, text

from api.dependencies import get_pg_url
from api.schemas import ProductListResponse, ProductSchema

router = APIRouter(prefix="/products", tags=["Products"])


def _get_engine():
    return create_engine(get_pg_url(), echo=False)


@router.get("", response_model=ProductListResponse)
def list_products() -> ProductListResponse:
    """Tra ve toan bo san pham trong Postgres."""
    try:
        engine = _get_engine()
        with engine.connect() as conn:
            rows = conn.execute(
                text(
                    "SELECT id, name, brand, price, specs, description FROM products ORDER BY id"
                )
            ).fetchall()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Loi Postgres: {e}")

    products = []
    for r in rows:
        products.append(
            ProductSchema(
                id=r.id,
                name=r.name,
                brand=r.brand,
                price=float(r.price),
                specs=json.loads(r.specs) if isinstance(r.specs, str) else r.specs,
                description=r.description,
            )
        )

    return ProductListResponse(total=len(products), products=products)


@router.get("/{product_id}", response_model=ProductSchema)
def get_product(product_id: int) -> ProductSchema:
    """Tra ve chi tiet mot san pham theo ID."""
    try:
        engine = _get_engine()
        with engine.connect() as conn:
            row = conn.execute(
                text(
                    "SELECT id, name, brand, price, specs, description FROM products WHERE id = :pid"
                ),
                {"pid": product_id},
            ).fetchone()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Loi Postgres: {e}")

    if not row:
        raise HTTPException(
            status_code=404, detail=f"Khong tim thay san pham id={product_id}"
        )

    return ProductSchema(
        id=row.id,
        name=row.name,
        brand=row.brand,
        price=float(row.price),
        specs=json.loads(row.specs) if isinstance(row.specs, str) else row.specs,
        description=row.description,
    )
