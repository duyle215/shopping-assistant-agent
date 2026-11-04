"""
Search service - hybrid search: tu khoa (PostgreSQL pg_trgm) + theo nghia (Qdrant),
gop bang Reciprocal Rank Fusion, ca hai dung chung bo loc co cau truc.

LLM bien cau hoi thanh tham so tool, vd "Samsung duoi 10 trieu pin trau" ->
query="pin trau", brand="Samsung", price_max=10_000_000, battery_min=5000.

- Tim theo nghia hop voi nhu cau ("chup dem dep", "choi game").
- Tim theo tu khoa hop voi ten may ("Redmi 13C" khac "Redmi Note 13"), cho embedding hay lan.
"""

from __future__ import annotations

import logging
from typing import Optional

from sqlalchemy import text

from app.agent.schemas import SearchResult
from app.catalog import normalize_brand
from app.config import EMBED_MODEL, OPENAI_API_KEY, OPENAI_BASE_URL, QDRANT_COLLECTION
from app.db import get_engine, get_qdrant

logger = logging.getLogger("search")

RRF_K = 60  # hang so chuan cua Reciprocal Rank Fusion
KEYWORD_MIN_SIMILARITY = 0.35


def _embed(query: str) -> list[float]:
    from openai import OpenAI

    client = OpenAI(base_url=OPENAI_BASE_URL, api_key=OPENAI_API_KEY)
    return client.embeddings.create(model=EMBED_MODEL, input=query).data[0].embedding


def _clean_filters(
    brand: Optional[str] = None,
    os: Optional[str] = None,
    price_min: Optional[float] = None,
    price_max: Optional[float] = None,
    ram_min: Optional[int] = None,
    battery_min: Optional[int] = None,
    storage_min: Optional[int] = None,
) -> dict:
    return {
        "brand": normalize_brand(brand) if brand else None,
        "os": ("iOS" if os.lower() == "ios" else "Android") if os else None,
        "price_min": price_min,
        "price_max": price_max,
        "ram_min": ram_min,
        "battery_min": battery_min,
        "storage_min": storage_min,
    }


def build_filter(**filters):
    """Qdrant Filter tu cac dieu kien; None neu khong co dieu kien nao."""
    from qdrant_client.models import FieldCondition, Filter, MatchValue, Range

    f = _clean_filters(**filters)
    must: list = []
    if f["brand"]:
        must.append(FieldCondition(key="brand", match=MatchValue(value=f["brand"])))
    if f["os"]:
        must.append(FieldCondition(key="os", match=MatchValue(value=f["os"])))
    if f["price_min"] is not None or f["price_max"] is not None:
        must.append(FieldCondition(key="price", range=Range(gte=f["price_min"], lte=f["price_max"])))
    if f["ram_min"] is not None:
        must.append(FieldCondition(key="ram_gb", range=Range(gte=f["ram_min"])))
    if f["battery_min"] is not None:
        must.append(FieldCondition(key="battery_mah", range=Range(gte=f["battery_min"])))
    if f["storage_min"] is not None:
        must.append(FieldCondition(key="max_storage_gb", range=Range(gte=f["storage_min"])))
    return Filter(must=must) if must else None


def _sql_filter(f: dict) -> tuple[str, dict]:
    clauses, params = [], {}
    if f["brand"]:
        clauses.append("brand = :brand")
        params["brand"] = f["brand"]
    if f["os"]:
        clauses.append("os = :os")
        params["os"] = f["os"]
    if f["price_min"] is not None:
        clauses.append("price >= :price_min")
        params["price_min"] = f["price_min"]
    if f["price_max"] is not None:
        clauses.append("price <= :price_max")
        params["price_max"] = f["price_max"]
    if f["ram_min"] is not None:
        clauses.append("ram_gb >= :ram_min")
        params["ram_min"] = f["ram_min"]
    if f["battery_min"] is not None:
        clauses.append("battery_mah >= :battery_min")
        params["battery_min"] = f["battery_min"]
    if f["storage_min"] is not None:
        clauses.append(":storage_min <= ANY(storage_gb)")
        params["storage_min"] = f["storage_min"]
    return (" AND ".join(clauses) or "TRUE"), params


# ------------------------------------------------------------------
# TUNG NGUON
# ------------------------------------------------------------------
def dense_ids(query_vector: list[float], limit: int, **filters) -> list[int]:
    hits = (
        get_qdrant()
        .query_points(
            collection_name=QDRANT_COLLECTION,
            query=query_vector,
            query_filter=build_filter(**filters),
            limit=limit,
            with_payload=["product_id"],
        )
        .points
    )
    return [h.payload["product_id"] for h in hits]


def keyword_ids(query: str, limit: int, **filters) -> list[int]:
    """Do giong ten may theo trigram (pg_trgm), chi giu ket qua du giong."""
    where, params = _sql_filter(_clean_filters(**filters))
    # word_similarity: truy van co nam trong ten khong ("iphone 15" khop ca "iPhone 15 Pro Max");
    # similarity tren ca chuoi de pha hoa, uu tien ten khop tron ("iPhone 15").
    sql = text(
        "SELECT id, word_similarity(lower(:q), lower(name)) AS sim, "
        "similarity(lower(:q), lower(name)) AS full_sim "
        f"FROM products WHERE {where} ORDER BY sim DESC, full_sim DESC, id LIMIT :limit"
    )
    try:
        with get_engine().connect() as conn:
            rows = conn.execute(sql, {**params, "q": query, "limit": limit}).fetchall()
    except Exception as exc:  # pg_trgm chua cai -> chi dung tim theo nghia
        logger.warning(f"[Search] Bo qua tim tu khoa: {exc}")
        return []
    return [r.id for r in rows if r.sim >= KEYWORD_MIN_SIMILARITY]


def rrf(rankings: list[list[int]], k: int = RRF_K) -> list[tuple[int, float]]:
    """Reciprocal Rank Fusion: diem = tong 1/(k + hang) tren cac danh sach."""
    scores: dict[int, float] = {}
    for ranking in rankings:
        for rank, pid in enumerate(ranking, start=1):
            scores[pid] = scores.get(pid, 0.0) + 1.0 / (k + rank)
    return sorted(scores.items(), key=lambda item: (-item[1], item[0]))


def _load(ids_scores: list[tuple[int, float]]) -> list[SearchResult]:
    if not ids_scores:
        return []
    ids = [pid for pid, _ in ids_scores]
    with get_engine().connect() as conn:
        rows = conn.execute(
            text(
                "SELECT id, name, brand, price, ram_gb, battery_mah, main_camera_mp, "
                "(SELECT max(s) FROM unnest(storage_gb) s) AS max_storage_gb "
                "FROM products WHERE id = ANY(:ids)"
            ),
            {"ids": ids},
        ).fetchall()
    by_id = {r.id: r for r in rows}
    return [
        SearchResult(
            product_id=r.id,
            name=r.name,
            brand=r.brand,
            price=int(r.price),
            ram_gb=r.ram_gb,
            battery_mah=r.battery_mah,
            max_storage_gb=r.max_storage_gb,
            main_camera_mp=r.main_camera_mp,
            score=round(score, 4),
        )
        for pid, score in ids_scores
        if (r := by_id.get(pid))
    ]


# ------------------------------------------------------------------
# API
# ------------------------------------------------------------------
def search_products(query: str, top_k: int = 5, mode: str = "hybrid", **filters) -> list[SearchResult]:
    """mode: 'hybrid' (mac dinh), 'dense' (chi theo nghia) hoac 'keyword'."""
    pool = max(top_k * 3, 10)
    rankings = []
    if mode in ("hybrid", "dense"):
        try:
            rankings.append(dense_ids(_embed(query), pool, **filters))
        except Exception as exc:
            # Vd het quota embedding: van tim duoc theo ten may
            if mode == "dense":
                raise
            logger.warning(f"[Search] Tim theo nghia loi, chi dung tu khoa: {exc}")
    if mode in ("hybrid", "keyword"):
        rankings.append(keyword_ids(query, pool, **filters))
    return _load(rrf(rankings)[:top_k])
