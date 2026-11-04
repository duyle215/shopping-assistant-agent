"""
Search service - tim san pham theo nghia (Qdrant) ket hop bo loc co cau truc.

LLM bien cau hoi thanh tham so tool, vd "Samsung duoi 10 trieu pin trau" ->
query="pin trau", brand="Samsung", price_max=10_000_000, battery_min=5000.
Bo loc chay tren payload Qdrant (gia, hang, RAM, pin, bo nho), sau do moi xep hang theo nghia.
"""

from __future__ import annotations

from typing import Optional

from app.agent.schemas import SearchResult
from app.catalog import normalize_brand
from app.config import EMBED_MODEL, OPENAI_API_KEY, OPENAI_BASE_URL, QDRANT_COLLECTION
from app.db import get_qdrant


def _embed(query: str) -> list[float]:
    from openai import OpenAI

    client = OpenAI(base_url=OPENAI_BASE_URL, api_key=OPENAI_API_KEY)
    return client.embeddings.create(model=EMBED_MODEL, input=query).data[0].embedding


def build_filter(
    brand: Optional[str] = None,
    os: Optional[str] = None,
    price_min: Optional[float] = None,
    price_max: Optional[float] = None,
    ram_min: Optional[int] = None,
    battery_min: Optional[int] = None,
    storage_min: Optional[int] = None,
):
    """Tao Qdrant Filter tu cac dieu kien; None neu khong co dieu kien nao."""
    from qdrant_client.models import FieldCondition, Filter, MatchValue, Range

    must: list = []
    if brand:
        must.append(FieldCondition(key="brand", match=MatchValue(value=normalize_brand(brand))))
    if os:
        must.append(FieldCondition(key="os", match=MatchValue(value="iOS" if os.lower() == "ios" else "Android")))
    if price_min is not None or price_max is not None:
        must.append(FieldCondition(key="price", range=Range(gte=price_min, lte=price_max)))
    if ram_min is not None:
        must.append(FieldCondition(key="ram_gb", range=Range(gte=ram_min)))
    if battery_min is not None:
        must.append(FieldCondition(key="battery_mah", range=Range(gte=battery_min)))
    if storage_min is not None:
        must.append(FieldCondition(key="max_storage_gb", range=Range(gte=storage_min)))
    return Filter(must=must) if must else None


def search_products(
    query: str,
    top_k: int = 5,
    **filters,
) -> list[SearchResult]:
    """Tim san pham: loc theo thong so truoc, roi xep hang theo do giong nghia."""
    hits = (
        get_qdrant()
        .query_points(
            collection_name=QDRANT_COLLECTION,
            query=_embed(query),
            query_filter=build_filter(**filters),
            limit=top_k,
            with_payload=True,
        )
        .points
    )

    return [
        SearchResult(
            product_id=h.payload["product_id"],
            name=h.payload["name"],
            brand=h.payload["brand"],
            price=h.payload["price"],
            ram_gb=h.payload["ram_gb"],
            battery_mah=h.payload["battery_mah"],
            max_storage_gb=h.payload["max_storage_gb"],
            main_camera_mp=h.payload["main_camera_mp"],
            score=round(h.score, 4),
        )
        for h in hits
    ]
