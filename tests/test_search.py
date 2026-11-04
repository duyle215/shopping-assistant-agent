"""Hybrid search: RRF, tim theo tu khoa trong PostgreSQL, bo loc, du phong khi embedding loi."""

from __future__ import annotations

from sqlalchemy import text

from app.services import search
from app.services.search import keyword_ids, rrf


def test_rrf_rewards_items_ranked_high_in_both_lists():
    fused = [pid for pid, _ in rrf([[1, 2, 3], [3, 2, 9]])]
    assert set(fused[:2]) == {2, 3}  # co mat o ca hai danh sach
    assert fused[-1] in (1, 9)
    assert set(fused) == {1, 2, 3, 9}


def _add(engine, pid, name, brand="Apple", price=20_000_000, os="iOS"):
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO products (id, name, brand, model, price, stock, chipset, ram_gb, "
                "storage_gb, screen_inch, refresh_rate_hz, battery_mah, main_camera_mp, os) "
                "VALUES (:id, :name, :brand, :name, :price, 5, 'Chip', 8, '{128,256}', 6.1, 60, "
                "4000, 48, :os)"
            ),
            {"id": pid, "name": name, "brand": brand, "price": price, "os": os},
        )


def test_keyword_prefers_exact_name(db):
    _add(db, 1, "iPhone 15 Pro Max", price=30_000_000)
    _add(db, 2, "iPhone 15")
    _add(db, 3, "Samsung Galaxy S24", brand="Samsung", os="Android")

    assert keyword_ids("iphone 15", 5)[:2] == [2, 1]
    assert 3 not in keyword_ids("iphone 15", 5)


def test_keyword_applies_filters(db):
    _add(db, 1, "iPhone 15 Pro Max", price=30_000_000)
    _add(db, 2, "iPhone 15", price=20_000_000)

    assert keyword_ids("iphone 15", 5, price_max=25_000_000) == [2]
    assert keyword_ids("iphone 15", 5, storage_min=512) == []


def test_hybrid_falls_back_to_keyword_when_embedding_fails(db, monkeypatch):
    _add(db, 2, "iPhone 15")

    def broken(_query):
        raise RuntimeError("quota exceeded")

    monkeypatch.setattr(search, "_embed", broken)

    results = search.search_products("iphone 15")
    assert [r.product_id for r in results] == [2]
