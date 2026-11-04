"""
Inventory service - ton kho va dat hang qua Odoo.

  - check_inventory:             so luong con ban duoc (free_qty: ton kho tru hang da giu cho don).
  - place_order:                 tao don ban (sale.order) qua method chat_place_order cua addon:
                                 du hang thi xac nhan don (Odoo giu hang cho phieu giao),
                                 thieu hang thi de bao gia cho nhan vien xu ly khi hang ve.
  - save_customer_info_to_order: gan ten + SDT vao bao gia dang cho cua phien chat.
"""

from __future__ import annotations

import logging

from app.odoo import OdooError, get_odoo
from app.services.product import BASE_DOMAIN

logger = logging.getLogger("inventory")

LOW_STOCK = 5


def stock_status(stock: int) -> str:
    if stock <= 0:
        return "out_of_stock"
    return "low_stock" if stock <= LOW_STOCK else "in_stock"


def check_inventory(product_id: int) -> dict:
    """Kiem tra ton kho cua san pham theo ID."""
    rows = get_odoo().search_read(
        "product.template",
        [("id", "=", int(product_id)), *BASE_DOMAIN],
        ["id", "name", "phone_brand", "list_price", "chat_free_qty"],
    )
    if not rows:
        return {"error": f"Khong tim thay san pham co ID = {product_id}"}
    r = rows[0]
    stock = int(r["chat_free_qty"])
    return {
        "product_id": r["id"],
        "name": r["name"],
        "brand": r["phone_brand"] or "",
        "price": float(r["list_price"]),
        "stock": stock,
        "status": stock_status(stock),
    }


def place_order(
    product_id: int,
    quantity: int,
    customer_name: str,
    customer_phone: str,
    session_id: str | None = None,
) -> dict:
    """Dat hang: mot transaction trong Odoo (khoa dong san pham, kiem tra ton, tao + xac nhan don)."""
    if quantity <= 0:
        return {"error": "So luong dat hang phai lon hon 0."}
    if not (customer_name or "").strip() or not (customer_phone or "").strip():
        return {"error": "Can ho ten va so dien thoai nguoi nhan de dat hang."}
    try:
        res = get_odoo().call(
            "sale.order",
            "chat_place_order",
            product_tmpl_id=int(product_id),
            quantity=int(quantity),
            customer_name=customer_name,
            customer_phone=customer_phone,
            session_id=session_id,
        )
    except OdooError as exc:
        logger.error(f"[Order] Odoo tu choi: {exc}")
        return {"error": f"Khong tao duoc don hang: {exc}"}

    if res.get("error"):
        return {"error": f"Khong tim thay san pham co ID = {product_id}"}

    name, ref = res["product_name"], res["order_ref"]
    if res["status"] == "confirmed":
        logger.info(f"[Order OK] {ref}: {name} x{quantity}, con {res['remaining_stock']}")
        return {
            "status": "confirmed",
            "order_ref": ref,
            "product_name": name,
            "quantity": quantity,
            "amount_total": res["amount_total"],
            "remaining_stock": res["remaining_stock"],
            "message": (
                f"Dat hang thanh cong! Ma don {ref}: {quantity} chiec {name}. "
                f"Con lai trong kho: {res['remaining_stock']} chiec."
            ),
        }

    current = res["free_qty_before"]
    logger.info(f"[Order PENDING] {ref}: {name} x{quantity}, kho con {current}")
    return {
        "status": "pending_restock",
        "order_ref": ref,
        "product_name": name,
        "quantity_requested": quantity,
        "current_stock": current,
        "shortage": res["shortage"],
        "message": (
            f"So luong hien tai trong kho khong du! Ban yeu cau {quantity} chiec {name} nhung "
            f"kho chi con {current} chiec (thieu {res['shortage']}). Da ghi nhan bao gia {ref} "
            f"va bao nhan vien nhap hang; nhan vien se goi lai {customer_name} khi hang ve."
        ),
    }


def save_customer_info_to_order(session_id: str, customer_name: str, customer_phone: str) -> dict:
    """Cap nhat ten + SDT vao bao gia (don cho hang) gan nhat cua phien chat."""
    res = get_odoo().call(
        "sale.order",
        "chat_update_customer",
        session_id=session_id,
        customer_name=customer_name,
        customer_phone=customer_phone,
    )
    if res.get("status") != "updated":
        return {"status": "no_pending_order", "message": "Khong co don hang nao can cap nhat."}
    return {
        "status": "updated",
        "message": (
            f"Da luu thong tin vao don {res['order_ref']}: {customer_name} - {customer_phone}. "
            "Nhan vien se lien he voi ban som nhat khi hang ve!"
        ),
    }
