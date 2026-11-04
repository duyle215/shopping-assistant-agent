"""Hybrid search: RRF, tim theo ten (trigram) tren Odoo, bo loc, du phong khi embedding loi."""

from __future__ import annotations

from app.services import search
from app.services.search import keyword_ids, rrf


def test_rrf_rewards_items_ranked_high_in_both_lists():
    fused = [pid for pid, _ in rrf([[1, 2, 3], [3, 2, 9]])]
    assert set(fused[:2]) == {2, 3}  # co mat o ca hai danh sach
    assert fused[-1] in (1, 9)
    assert set(fused) == {1, 2, 3, 9}


def test_trigram_similarity_prefers_whole_name():
    assert search.word_similarity("iphone 15", "iPhone 15 Pro Max") == 1.0
    assert search.similarity("iphone 15", "iPhone 15") > search.similarity("iphone 15", "iPhone 15 Pro Max")
    assert search.word_similarity("redmi 13c", "Xiaomi Redmi Note 13") < 1.0


def test_keyword_prefers_exact_name(odoo, add_phone):
    pro_max = add_phone("iPhone 15 Pro Max", price=30_000_000)
    base = add_phone("iPhone 15")
    s24 = add_phone("Samsung Galaxy S24", brand="Samsung", os="Android")

    assert keyword_ids("iphone 15", 5)[:2] == [base, pro_max]
    assert s24 not in keyword_ids("iphone 15", 5)


def test_keyword_applies_filters(odoo, add_phone):
    add_phone("iPhone 15 Pro Max", price=30_000_000, storage_gb="256,512")
    base = add_phone("iPhone 15", price=20_000_000)

    assert keyword_ids("iphone 15", 5, price_max=25_000_000) == [base]
    assert keyword_ids("iphone 15", 5, storage_min=1024) == []


def test_hybrid_falls_back_to_keyword_when_embedding_fails(odoo, add_phone, monkeypatch):
    base = add_phone("iPhone 15")

    def broken(_query):
        raise RuntimeError("quota exceeded")

    monkeypatch.setattr(search, "_embed", broken)

    results = search.search_products("iphone 15")
    assert [r.product_id for r in results] == [base]


def test_keyword_refresh_rate_filter(odoo, add_phone):
    fast = add_phone("iPhone 15", refresh_rate_hz=165)
    add_phone("iPhone 15 Plus")

    assert keyword_ids("iphone 15", 5, refresh_rate_min=144) == [fast]


def test_sort_by_uses_real_specs_and_filters(odoo, add_phone):
    a = add_phone("Phone A", price=30_000_000)
    b = add_phone("Phone B", price=10_000_000)
    c = add_phone("Phone C", price=20_000_000, refresh_rate_hz=165)

    assert [r.product_id for r in search.search_products("re nhat", sort_by="price_asc")] == [b, c, a]
    assert search.search_products("game", sort_by="refresh_rate_desc", top_k=1)[0].product_id == c
    assert [r.product_id for r in search.search_products("x", sort_by="price_desc", price_max=25_000_000)] == [c, b]


def test_archived_or_stale_results_are_dropped(odoo, add_phone):
    """Ket qua (vd tu Qdrant) duoc loc lai tren Odoo: may da an hoac gia da doi thi bi bo."""
    keep = add_phone("Phone A", price=10_000_000)
    hidden = add_phone("Phone B", price=10_000_000)
    odoo.write("product.template", [hidden], {"active": False})

    loaded = search._load([(hidden, 0.9), (keep, 0.5)], price_max=12_000_000)
    assert [r.product_id for r in loaded] == [keep]
    odoo.write("product.template", [keep], {"list_price": 15_000_000})
    assert search._load([(keep, 0.5)], price_max=12_000_000) == []
