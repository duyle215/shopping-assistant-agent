"""
Search service - hybrid search: tu khoa (trigram tren ten san pham Odoo) + theo nghia (Qdrant),
gop bang Reciprocal Rank Fusion, ca hai dung chung bo loc co cau truc (domain Odoo / filter Qdrant).

LLM bien cau hoi thanh tham so tool, vd "Samsung duoi 10 trieu pin trau" ->
query="pin trau", brand="Samsung", price_max=10_000_000, battery_min=5000.

- Tim theo nghia hop voi nhu cau ("chup dem dep", "choi game").
- Tim theo tu khoa hop voi ten may ("Redmi 13C" khac "Redmi Note 13"), cho embedding hay lan.
"""

from __future__ import annotations

import logging
import re
from typing import Optional

from app.agent.schemas import SearchResult
from app.catalog import normalize_brand
from app.config import EMBED_MODEL, OPENAI_API_KEY, OPENAI_BASE_URL, QDRANT_COLLECTION
from app.db import get_qdrant
from app.odoo import get_odoo

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
    refresh_rate_min: Optional[int] = None,
) -> dict:
    return {
        "brand": normalize_brand(brand) if brand else None,
        "os": ("iOS" if os.lower() == "ios" else "Android") if os else None,
        "price_min": price_min,
        "price_max": price_max,
        "ram_min": ram_min,
        "battery_min": battery_min,
        "storage_min": storage_min,
        "refresh_rate_min": refresh_rate_min,
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
    if f["refresh_rate_min"] is not None:
        must.append(FieldCondition(key="refresh_rate_hz", range=Range(gte=f["refresh_rate_min"])))
    return Filter(must=must) if must else None


def odoo_domain(f: dict) -> list:
    """Bo loc da chuan hoa -> domain Odoo tren product.template."""
    from app.services.product import BASE_DOMAIN

    domain = list(BASE_DOMAIN)
    if f["brand"]:
        domain.append(("phone_brand", "=", f["brand"]))
    if f["os"]:
        domain.append(("phone_os", "=", f["os"]))
    if f["price_min"] is not None:
        domain.append(("list_price", ">=", f["price_min"]))
    if f["price_max"] is not None:
        domain.append(("list_price", "<=", f["price_max"]))
    if f["ram_min"] is not None:
        domain.append(("phone_ram_gb", ">=", f["ram_min"]))
    if f["battery_min"] is not None:
        domain.append(("phone_battery_mah", ">=", f["battery_min"]))
    if f["storage_min"] is not None:
        domain.append(("phone_max_storage_gb", ">=", f["storage_min"]))
    if f["refresh_rate_min"] is not None:
        domain.append(("phone_refresh_rate_hz", ">=", f["refresh_rate_min"]))
    return domain


# ------------------------------------------------------------------
# DO GIONG TEN (trigram, nhu pg_trgm)
# ------------------------------------------------------------------
def trigrams(text: str) -> set[str]:
    """Trigram theo tung tu, giong pg_trgm: tu viet thuong, them 2 dau cach truoc, 1 sau."""
    out: set[str] = set()
    for word in re.findall(r"[0-9a-z\u00c0-\u1ef9]+", text.lower()):
        padded = f"  {word} "
        out.update(padded[i : i + 3] for i in range(len(padded) - 2))
    return out


def word_similarity(query: str, name: str) -> float:
    """Ti le trigram cua truy van co trong ten ("iphone 15" nam tron trong "iPhone 15 Pro Max")."""
    q = trigrams(query)
    return len(q & trigrams(name)) / len(q) if q else 0.0


def similarity(a: str, b: str) -> float:
    """Do giong ca chuoi (Jaccard tren trigram) de pha hoa: uu tien ten khop tron."""
    ta, tb = trigrams(a), trigrams(b)
    return len(ta & tb) / len(ta | tb) if ta | tb else 0.0


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
    """Do giong ten may theo trigram tren cac san pham thoa bo loc (lay tu Odoo)."""
    rows = get_odoo().search_read(
        "product.template", odoo_domain(_clean_filters(**filters)), ["id", "name"]
    )
    scored = [
        (word_similarity(query, r["name"]), similarity(query, r["name"]), r["id"]) for r in rows
    ]
    scored.sort(key=lambda s: (-s[0], -s[1], s[2]))
    return [pid for sim, _, pid in scored[:limit] if sim >= KEYWORD_MIN_SIMILARITY]


def rrf(rankings: list[list[int]], k: int = RRF_K) -> list[tuple[int, float]]:
    """Reciprocal Rank Fusion: diem = tong 1/(k + hang) tren cac danh sach."""
    scores: dict[int, float] = {}
    for ranking in rankings:
        for rank, pid in enumerate(ranking, start=1):
            scores[pid] = scores.get(pid, 0.0) + 1.0 / (k + rank)
    return sorted(scores.items(), key=lambda item: (-item[1], item[0]))


LOAD_FIELDS = [
    "id",
    "name",
    "list_price",
    "phone_brand",
    "phone_ram_gb",
    "phone_battery_mah",
    "phone_max_storage_gb",
    "phone_main_camera_mp",
    "phone_refresh_rate_hz",
]


def _load(ids_scores: list[tuple[int, float]], **filters) -> list[SearchResult]:
    """Doc ket qua tu Odoo. Bo loc chay lai o day, nen payload Qdrant cu (vd gia vua doi
    tren Odoo) hay san pham da an khong lot vao ket qua."""
    if not ids_scores:
        return []
    ids = [pid for pid, _ in ids_scores]
    domain = [("id", "in", ids), *odoo_domain(_clean_filters(**filters))]
    by_id = {r["id"]: r for r in get_odoo().search_read("product.template", domain, LOAD_FIELDS)}
    return [
        SearchResult(
            product_id=r["id"],
            name=r["name"],
            brand=r["phone_brand"] or "",
            price=int(round(r["list_price"])),
            ram_gb=r["phone_ram_gb"],
            battery_mah=r["phone_battery_mah"],
            max_storage_gb=r["phone_max_storage_gb"],
            main_camera_mp=r["phone_main_camera_mp"],
            refresh_rate_hz=r["phone_refresh_rate_hz"],
            score=round(score, 4),
        )
        for pid, score in ids_scores
        if (r := by_id.get(pid))
    ]


# Cau hoi "nhat" (re nhat, pin trau nhat...): Odoo sap xep tren du lieu that
SORTS: dict[str, str] = {
    "price_asc": "list_price asc",
    "price_desc": "list_price desc",
    "battery_desc": "phone_battery_mah desc",
    "ram_desc": "phone_ram_gb desc",
    "refresh_rate_desc": "phone_refresh_rate_hz desc",
    "storage_desc": "phone_max_storage_gb desc",
    "camera_desc": "phone_main_camera_mp desc",
}


def sorted_ids(sort_by: str, limit: int, **filters) -> list[int]:
    if sort_by not in SORTS:
        raise ValueError(f"sort_by phai la mot trong {list(SORTS)}")
    return get_odoo().search(
        "product.template", odoo_domain(_clean_filters(**filters)), order=f"{SORTS[sort_by]}, id", limit=limit
    )


# ------------------------------------------------------------------
# API
# ------------------------------------------------------------------
def search_products(
    query: str, top_k: int = 5, mode: str = "hybrid", sort_by: Optional[str] = None, **filters
) -> list[SearchResult]:
    """mode: 'hybrid' (mac dinh), 'dense' (chi theo nghia) hoac 'keyword'.
    sort_by: sap xep theo thong so thay vi do giong nghia (vd 'refresh_rate_desc')."""
    if sort_by:
        return _load([(pid, 0.0) for pid in sorted_ids(sort_by, top_k, **filters)], **filters)
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
    return _load(rrf(rankings)[:top_k], **filters)
