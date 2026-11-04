"""
Dong bo catalog vao Odoo roi vao Qdrant.

Doc data/catalog.jsonl (tao boi scripts/extract_catalog.py), bo qua ban ghi khong hop le, roi:
  - Odoo:   tao / cap nhat product.template theo ma noi bo PHONE-<id> (gia, thong so phone_*,
            dang tren website), dat ton kho theo data/stock.json (stock.quant, che do kiem kho).
  - Qdrant: vector cua text san pham + payload thong so de loc; product_id = id product.template.

Can user catalog-sync (admin_api_key trong odoo/secrets/<db>.json, do odoo-setup tao).

Chay:  python scripts/sync_odoo.py
       python scripts/sync_odoo.py --db odoo_eval            # database Odoo khac
       python scripts/sync_odoo.py --skip-qdrant             # chi Odoo (vd dat lai ton kho)
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


def default_code(catalog_id: int) -> str:
    return f"PHONE-{catalog_id:03d}"


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
                "catalog_id": rec["id"],
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


def summary_text(p: dict) -> str:
    storage = "/".join(f"{s}GB" for s in p["storage_gb"])
    return (
        f"{p['name']} ({p['brand']}, {p['os']}). Chip {p['chipset']}, RAM {p['ram_gb']}GB, "
        f"bo nho {storage}, man hinh {p['screen_inch']} inch {p['refresh_rate_hz']}Hz, "
        f"pin {p['battery_mah']}mAh, camera {p['main_camera_mp']}MP."
    )


def spec_line(p: dict) -> str:
    """Mo ta ngan tren website Odoo: mot dong thong so, khong phu thuoc ngon ngu."""
    storage = " / ".join(f"{s // 1024} TB" if s >= 1024 else f"{s} GB" for s in p["storage_gb"])
    parts = [
        p["chipset"],
        f"RAM {p['ram_gb']} GB",
        storage,
        f'{p["screen_inch"]}" {p["refresh_rate_hz"]} Hz',
        f"{p['battery_mah']} mAh" + (f" · {p['charging_w']} W" if p.get("charging_w") else ""),
        f"{p['main_camera_mp']} MP",
    ]
    return " · ".join(parts)


def embedding_text(p: dict) -> str:
    """Text de embed: ten + thong so tom tat + noi dung trang."""
    return f"{summary_text(p)}\n{p['description'][:3000]}"


def odoo_vals(p: dict) -> dict:
    return {
        "name": p["name"],
        "default_code": default_code(p["catalog_id"]),
        "type": "consu",
        "is_storable": True,
        "sale_ok": True,
        "purchase_ok": True,
        "is_published": True,
        "list_price": p["price_vnd"],
        "taxes_id": [(6, 0, [])],  # gia ban le da gom VAT
        "description_sale": spec_line(p),
        "is_phone": True,
        "phone_brand": p["brand"],
        "phone_model": p["model"],
        "phone_chipset": p["chipset"],
        "phone_ram_gb": p["ram_gb"],
        "phone_storage_gb": ",".join(str(s) for s in p["storage_gb"]),
        "phone_screen_inch": p["screen_inch"],
        "phone_refresh_rate_hz": p["refresh_rate_hz"],
        "phone_battery_mah": p["battery_mah"],
        "phone_charging_w": p["charging_w"] or 0,
        "phone_main_camera_mp": p["main_camera_mp"],
        "phone_weight_g": p["weight_g"] or 0,
        "phone_os": p["os"],
        "phone_release_year": p["release_year"] or 0,
    }


def sync_products(odoo, products: list[dict]) -> dict[int, int]:
    """Upsert product.template theo default_code. Tra ve {catalog_id: product.template id}."""
    codes = [default_code(p["catalog_id"]) for p in products]
    existing = {
        r["default_code"]: r["id"]
        for r in odoo.search_read(
            "product.template",
            [("default_code", "in", codes)],
            ["id", "default_code"],
            context={"active_test": False},
        )
    }
    ids: dict[int, int] = {}
    created = 0
    for p in products:
        vals = odoo_vals(p)
        tmpl_id = existing.get(vals["default_code"])
        if tmpl_id:
            odoo.write("product.template", [tmpl_id], {**vals, "active": True})
        else:
            tmpl_id = odoo.create("product.template", vals)
            created += 1
        ids[p["catalog_id"]] = tmpl_id
    print(f"  Odoo: {created} san pham moi, {len(products) - created} cap nhat")
    return ids


def set_stock(odoo, levels: dict[int, int], quiet: bool = False) -> None:
    """Dat so luong ton kho (product.template id -> so luong) o kho chinh, nhu mot lan kiem kho."""
    location = odoo.search_read("stock.warehouse", [], ["lot_stock_id"], limit=1)[0]["lot_stock_id"][0]
    variants = odoo.search_read(
        "product.product", [("product_tmpl_id", "in", list(levels))], ["id", "product_tmpl_id"]
    )
    quant_ids = []
    for v in variants:
        quant_ids.append(
            odoo.create(
                "stock.quant",
                {
                    "product_id": v["id"],
                    "location_id": location,
                    "inventory_quantity": levels[v["product_tmpl_id"][0]],
                },
                context={"inventory_mode": True},
            )
        )
    odoo.call("stock.quant", "action_apply_inventory", ids=quant_ids, context={"inventory_mode": True})
    if not quiet:
        print(f"  Odoo: da dat ton kho cho {len(quant_ids)} san pham")


def ingest_qdrant(products: list[dict], ids: dict[int, int]) -> int:
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
            pid = ids[p["catalog_id"]]
            points.append(
                PointStruct(
                    id=pid,
                    vector=item.embedding,
                    payload={
                        "product_id": pid,
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
    from app.odoo import get_odoo

    parser = argparse.ArgumentParser()
    parser.add_argument("--catalog", nargs="+", default=["data/catalog.jsonl"])
    parser.add_argument("--stock", default="data/stock.json")
    parser.add_argument("--db", default=None, help="Database Odoo (mac dinh ODOO_DB)")
    parser.add_argument("--skip-qdrant", action="store_true")
    args = parser.parse_args()

    print("=" * 55)
    print("  Shopping Assistant  |  Sync catalog -> Odoo -> Qdrant")
    print("=" * 55)

    for path in args.catalog:
        if not os.path.exists(path):
            sys.exit(f"Khong thay {path}. Chay scripts/extract_catalog.py truoc.")
    products = load_catalog(args.catalog, args.stock)
    print(f"\nDoc {len(products)} san pham hop le tu {', '.join(args.catalog)}")

    odoo = get_odoo(admin=True, db=args.db)
    print(f"\n[1/2] Odoo ({odoo.url}, database '{odoo.db}')...")
    ids = sync_products(odoo, products)
    set_stock(odoo, {ids[p["catalog_id"]]: p["stock"] for p in products})

    if args.skip_qdrant:
        print("\nBo qua Qdrant (--skip-qdrant)")
        return

    print("\n[2/2] Tao embedding va nap vector vao Qdrant...")
    print(f"  Embedding model: {EMBED_MODEL}")
    try:
        qd_count = ingest_qdrant(products, ids)
        print(f"  Qdrant: da upsert {qd_count} vector vao collection '{QDRANT_COLLECTION}'")
    except Exception as e:
        print(f"  Qdrant FAIL: {e}")
        if "already accessed" in str(e):
            print("  -> Qdrant local chi cho 1 process mo. Tat app (run.py) roi chay lai,")
            print("     hoac dung Qdrant server (QDRANT_URL, xem docker-compose.yml).")
        sys.exit(1)

    print()
    print("-" * 55)
    print(f"  Odoo    ->  {len(ids)} san pham (product.template, ma PHONE-xxx)")
    print(f"  Qdrant  ->  {qd_count} vector (collection: {QDRANT_COLLECTION})")
    print("-" * 55)
    print("  Hoan tat! San sang chay:  python run.py")

    from app.db import get_qdrant

    get_qdrant().close()


if __name__ == "__main__":
    main()
