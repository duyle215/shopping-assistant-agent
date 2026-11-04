"""
Ingest Data - nap catalog da trich xuat vao PostgreSQL va Qdrant.

Doc data/catalog.jsonl (tao boi scripts/extract_catalog.py), bo qua ban ghi khong hop le,
lay ton kho tu data/stock.json, roi:
  - PostgreSQL: moi thong so mot cot co kieu (bang products), tao lai bang orders/support_requests
  - Qdrant:     vector cua text san pham + payload thong so de loc (gia, hang, pin, RAM...)

Chay:  python scripts/ingest_data.py
       python scripts/ingest_data.py --catalog data/catalog.jsonl data/catalog_crawled.jsonl
"""

from __future__ import annotations

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.config import (  # noqa: E402
    EMBED_DIM,
    EMBED_MODEL,
    OPENAI_API_KEY,
    OPENAI_BASE_URL,
    QDRANT_COLLECTION,
    QDRANT_URL,
)

DEFAULT_STOCK = 10
EMBED_BATCH = 16


def load_catalog(paths: list[str], stock_path: str) -> list[dict]:
    from app.catalog import display_name

    stock: dict[str, int] = {}
    if os.path.exists(stock_path):
        with open(stock_path, encoding="utf-8") as f:
            stock = json.load(f)

    products, skipped = [], 0
    seen: set[int] = set()
    records = []
    for path in paths:
        with open(path, encoding="utf-8") as f:
            records += [json.loads(line) for line in f if line.strip()]
    for rec in records:
        if rec["id"] in seen:
            skipped += 1
            print(f"  Bo qua #{rec['id']} ({rec['source']}): trung id")
            continue
        seen.add(rec["id"])
        if not rec.get("valid") or not rec.get("spec"):
            skipped += 1
            print(f"  Bo qua #{rec['id']} ({rec['source']}): {rec.get('problems')}")
            continue
        spec = rec["spec"]
        products.append(
            {
                "id": rec["id"],
                "name": display_name(spec["brand"], spec["model"]),
                "stock": int(stock.get(str(rec["id"]), DEFAULT_STOCK)),
                "description": rec["text"],
                "source": rec["source"],
                **spec,
            }
        )
    if skipped:
        print(f"  Da bo qua {skipped} ban ghi")
    return products


def embedding_text(p: dict) -> str:
    """Text de embed: ten + thong so tom tat + noi dung trang."""
    storage = "/".join(f"{s}GB" for s in p["storage_gb"])
    summary = (
        f"{p['name']} ({p['brand']}, {p['os']}). Chip {p['chipset']}, RAM {p['ram_gb']}GB, "
        f"bo nho {storage}, man hinh {p['screen_inch']} inch {p['refresh_rate_hz']}Hz, "
        f"pin {p['battery_mah']}mAh, camera {p['main_camera_mp']}MP."
    )
    return f"{summary}\n{p['description'][:3000]}"


def ingest_postgres(products: list[dict]) -> int:
    from sqlalchemy.orm import Session

    from app.db import get_engine
    from app.models import Product, reset_db

    engine = get_engine()
    reset_db(engine)

    with Session(engine) as session:
        for p in products:
            session.add(
                Product(
                    id=p["id"],
                    name=p["name"],
                    brand=p["brand"],
                    model=p["model"],
                    price=p["price_vnd"],
                    stock=p["stock"],
                    chipset=p["chipset"],
                    ram_gb=p["ram_gb"],
                    storage_gb=p["storage_gb"],
                    screen_inch=p["screen_inch"],
                    refresh_rate_hz=p["refresh_rate_hz"],
                    battery_mah=p["battery_mah"],
                    charging_w=p["charging_w"],
                    main_camera_mp=p["main_camera_mp"],
                    weight_g=p["weight_g"],
                    os=p["os"],
                    release_year=p["release_year"],
                    description=p["description"],
                    source=p["source"],
                )
            )
        session.commit()
    return len(products)


def ingest_qdrant(products: list[dict]) -> int:
    from openai import OpenAI
    from qdrant_client.models import Distance, PayloadSchemaType, PointStruct, VectorParams

    from app.db import get_qdrant

    oai = OpenAI(base_url=OPENAI_BASE_URL, api_key=OPENAI_API_KEY)
    qdrant = get_qdrant()

    if qdrant.collection_exists(QDRANT_COLLECTION):
        qdrant.delete_collection(QDRANT_COLLECTION)
    qdrant.create_collection(
        collection_name=QDRANT_COLLECTION,
        vectors_config=VectorParams(size=EMBED_DIM, distance=Distance.COSINE),
    )
    # Index payload de loc nhanh (chi co tac dung voi Qdrant server)
    indexes = {
        "brand": PayloadSchemaType.KEYWORD,
        "os": PayloadSchemaType.KEYWORD,
        "price": PayloadSchemaType.INTEGER,
        "ram_gb": PayloadSchemaType.INTEGER,
        "battery_mah": PayloadSchemaType.INTEGER,
        "max_storage_gb": PayloadSchemaType.INTEGER,
    }
    if QDRANT_URL:
        for field, kind in indexes.items():
            qdrant.create_payload_index(QDRANT_COLLECTION, field, kind)

    points = []
    for start in range(0, len(products), EMBED_BATCH):
        batch = products[start : start + EMBED_BATCH]
        resp = oai.embeddings.create(model=EMBED_MODEL, input=[embedding_text(p) for p in batch])
        for p, item in zip(batch, resp.data):
            points.append(
                PointStruct(
                    id=p["id"],
                    vector=item.embedding,
                    payload={
                        "product_id": p["id"],
                        "name": p["name"],
                        "brand": p["brand"],
                        "os": p["os"],
                        "price": p["price_vnd"],
                        "ram_gb": p["ram_gb"],
                        "battery_mah": p["battery_mah"],
                        "max_storage_gb": max(p["storage_gb"]),
                        "main_camera_mp": p["main_camera_mp"],
                        "refresh_rate_hz": p["refresh_rate_hz"],
                    },
                )
            )

    qdrant.upsert(collection_name=QDRANT_COLLECTION, points=points)
    return len(points)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--catalog", nargs="+", default=["data/catalog.jsonl"])
    parser.add_argument("--stock", default="data/stock.json")
    args = parser.parse_args()

    print("=" * 55)
    print("  Shopping Assistant  |  Ingest Data")
    print("=" * 55)

    for path in args.catalog:
        if not os.path.exists(path):
            sys.exit(f"Khong thay {path}. Chay scripts/extract_catalog.py truoc.")
    products = load_catalog(args.catalog, args.stock)
    print(f"\nDoc {len(products)} san pham hop le tu {', '.join(args.catalog)}")

    print("\n[1/2] Nap du lieu vao PostgreSQL...")
    try:
        pg_count = ingest_postgres(products)
        print(f"  PostgreSQL: da luu {pg_count} san pham vao bang 'products'")
    except Exception as e:
        print(f"  PostgreSQL FAIL: {e}")
        sys.exit(1)

    print("\n[2/2] Tao embedding va nap vector vao Qdrant...")
    print(f"  Embedding model: {EMBED_MODEL}")
    try:
        qd_count = ingest_qdrant(products)
        print(f"  Qdrant: da upsert {qd_count} vector vao collection '{QDRANT_COLLECTION}'")
    except Exception as e:
        print(f"  Qdrant FAIL: {e}")
        if "already accessed" in str(e):
            print("  -> Qdrant local chi cho 1 process mo. Tat app (run.py) roi chay lai,")
            print("     hoac dung Qdrant server (QDRANT_URL, xem docker-compose.yml).")
        sys.exit(1)

    print()
    print("-" * 55)
    print(f"  PostgreSQL  ->  {pg_count} ban ghi  (bang: products)")
    print(f"  Qdrant      ->  {qd_count} vector   (collection: {QDRANT_COLLECTION})")
    print("-" * 55)
    print("  Hoan tat! San sang chay:  python run.py")

    from app.db import get_qdrant

    get_qdrant().close()


if __name__ == "__main__":
    main()
