"""
Product service - doc san pham tu Odoo (product.template, thong so o cac truong phone_*
cua addon shopping_assistant_chat). product_id trong toan bo app la id cua product.template.
"""

from __future__ import annotations

from typing import Optional

from app.agent.schemas import ProductMetadata
from app.odoo import get_odoo

MODEL = "product.template"
# Chi san pham dien thoai dang ban
BASE_DOMAIN = [("is_phone", "=", True), ("sale_ok", "=", True)]

SPEC_FIELDS = [
    "id",
    "name",
    "list_price",
    "chat_free_qty",
    "phone_brand",
    "phone_model",
    "phone_chipset",
    "phone_ram_gb",
    "phone_storage_gb",
    "phone_screen_inch",
    "phone_refresh_rate_hz",
    "phone_battery_mah",
    "phone_charging_w",
    "phone_main_camera_mp",
    "phone_weight_g",
    "phone_os",
    "phone_release_year",
]


def storage_list(value) -> list[int]:
    return [int(s) for s in str(value or "").split(",") if s.strip().isdigit()]


def to_model(rec: dict) -> ProductMetadata:
    """Ban ghi Odoo -> ProductMetadata. Odoo tra False cho truong rong; 0 cung coi la khong co."""

    def opt(key):
        return rec.get(key) or None

    return ProductMetadata(
        id=rec["id"],
        name=rec["name"],
        brand=rec.get("phone_brand") or "",
        model=rec.get("phone_model") or rec["name"],
        price=int(round(rec.get("list_price") or 0)),
        stock=int(rec.get("chat_free_qty") or 0),
        chipset=rec.get("phone_chipset") or "",
        ram_gb=rec.get("phone_ram_gb") or 0,
        storage_gb=storage_list(rec.get("phone_storage_gb")),
        screen_inch=rec.get("phone_screen_inch") or 0.0,
        refresh_rate_hz=rec.get("phone_refresh_rate_hz") or 0,
        battery_mah=rec.get("phone_battery_mah") or 0,
        charging_w=opt("phone_charging_w"),
        main_camera_mp=rec.get("phone_main_camera_mp") or 0,
        weight_g=opt("phone_weight_g"),
        os=rec.get("phone_os") or "",
        release_year=opt("phone_release_year"),
    )


def get_product_details(product_id: int) -> Optional[ProductMetadata]:
    """Lay thong so ky thuat chi tiet mot san pham."""
    products = get_products([product_id])
    return products[0] if products else None


def get_products(product_ids: list[int]) -> list[ProductMetadata]:
    """Lay nhieu san pham, giu dung thu tu product_ids."""
    ids = [int(i) for i in product_ids if str(i).lstrip("-").isdigit()]
    if not ids:
        return []
    rows = get_odoo().search_read(MODEL, [("id", "in", ids), *BASE_DOMAIN], SPEC_FIELDS)
    by_id = {r["id"]: to_model(r) for r in rows}
    return [by_id[i] for i in ids if i in by_id]


def list_products() -> list[ProductMetadata]:
    rows = get_odoo().search_read(MODEL, BASE_DOMAIN, SPEC_FIELDS, order="id")
    return [to_model(r) for r in rows]
