"""
Search service - Tim kiem san pham bang Qdrant semantic search.
"""

from __future__ import annotations

from typing import Optional

from app.config import (
    EMBED_MODEL,
    OPENAI_API_KEY,
    OPENAI_BASE_URL,
    QDRANT_COLLECTION,
    QDRANT_PATH,
)
from app.agent.schemas import SearchResult


# ------------------------------------------------------------------
# BRAND NORMALIZE MAP
# ------------------------------------------------------------------
BRAND_NORMALIZE_MAP: dict[str, str] = {
    "apple": "Apple",
    "iphone": "Apple",
    "samsung": "Samsung",
    "galaxy": "Samsung",
    "xiaomi": "Xiaomi",
    "mi": "Xiaomi",
    "redmi": "Xiaomi",
    "oppo": "OPPO",
    "google": "Google",
    "pixel": "Google",
}


def _normalize_brand(raw: Optional[str]) -> Optional[str]:
    """Chuan hoa ten thuong hieu cho khop voi du lieu Qdrant."""
    if not raw:
        return None
    key = raw.strip().lower()
    return BRAND_NORMALIZE_MAP.get(key, raw)


# ------------------------------------------------------------------
# SEARCH
# ------------------------------------------------------------------
def search_products(
    query: str,
    brand_filter: Optional[str] = None,
    max_price: Optional[float] = None,
    top_k: int = 3,
) -> list[SearchResult]:
    """Tim san pham trong Qdrant bang semantic search."""
    from openai import OpenAI as OAIClient
    from qdrant_client import QdrantClient
    from qdrant_client.models import FieldCondition, Filter, MatchValue, Range

    brand_filter = _normalize_brand(brand_filter)

    embed_client = OAIClient(base_url=OPENAI_BASE_URL, api_key=OPENAI_API_KEY)
    resp = embed_client.embeddings.create(model=EMBED_MODEL, input=query)
    query_vector = resp.data[0].embedding

    conditions: list = []
    if brand_filter:
        conditions.append(
            FieldCondition(key="brand", match=MatchValue(value=brand_filter))
        )
    if max_price:
        conditions.append(FieldCondition(key="price", range=Range(lte=max_price)))

    qdrant_filter = Filter(must=conditions) if conditions else None

    qdrant = QdrantClient(path=QDRANT_PATH)
    hits = qdrant.query_points(
        collection_name=QDRANT_COLLECTION,
        query=query_vector,
        query_filter=qdrant_filter,
        limit=top_k,
        with_payload=True,
    ).points

    results: list[SearchResult] = []
    for hit in hits:
        p = hit.payload
        results.append(
            SearchResult(
                product_id=p["product_id"],
                name=p["name"],
                brand=p["brand"],
                price=p["price"],
                score=round(hit.score, 4),
                description=p["description"],
            )
        )
    return results
