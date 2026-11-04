"""place_order: tru kho dung, khong ban vuot ton kho khi nhieu nguoi dat cung luc."""

from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor

from sqlalchemy import text

from app.services.inventory import place_order


def _add_product(engine, product_id: int = 1, stock: int = 1) -> None:
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO products (id, name, brand, model, price, stock, chipset, "
                "ram_gb, storage_gb, screen_inch, refresh_rate_hz, battery_mah, "
                "main_camera_mp, os) VALUES (:id, 'Test Phone', 'TestBrand', 'Phone', "
                "1000000, :stock, 'Chip', 8, '{128}', 6.1, 60, 4000, 12, 'Android')"
            ),
            {"id": product_id, "stock": stock},
        )


def _stock(engine, product_id: int = 1) -> int:
    with engine.connect() as conn:
        return conn.execute(
            text("SELECT stock FROM products WHERE id = :id"), {"id": product_id}
        ).scalar_one()


def _order_statuses(engine) -> list[str]:
    with engine.connect() as conn:
        return [r.status for r in conn.execute(text("SELECT status FROM orders"))]


def test_order_deducts_stock(db):
    _add_product(db, stock=3)

    result = place_order(product_id=1, quantity=2)

    assert result["status"] == "confirmed"
    assert result["remaining_stock"] == 1
    assert _stock(db) == 1


def test_order_larger_than_stock_becomes_pending_restock(db):
    _add_product(db, stock=1)

    result = place_order(product_id=1, quantity=3)

    assert result["status"] == "pending_restock"
    assert result["shortage"] == 2
    assert _stock(db) == 1


def test_rejects_non_positive_quantity(db):
    _add_product(db, stock=1)

    assert "error" in place_order(product_id=1, quantity=0)
    assert _order_statuses(db) == []


def test_unknown_product(db):
    assert "error" in place_order(product_id=999, quantity=1)


def test_concurrent_buyers_cannot_oversell_last_unit(db):
    """Nhieu khach bam dat cung luc mon cuoi cung: chi dung 1 don duoc xac nhan."""
    buyers = 8
    rounds = 5

    for round_no in range(rounds):
        product_id = 100 + round_no
        _add_product(db, product_id=product_id, stock=1)
        start = threading.Barrier(buyers)

        def buy(_):
            start.wait()
            return place_order(product_id=product_id, quantity=1)

        with ThreadPoolExecutor(max_workers=buyers) as pool:
            results = list(pool.map(buy, range(buyers)))

        statuses = [r["status"] for r in results]
        assert statuses.count("confirmed") == 1, statuses
        assert statuses.count("pending_restock") == buyers - 1, statuses
        assert _stock(db, product_id) == 0
