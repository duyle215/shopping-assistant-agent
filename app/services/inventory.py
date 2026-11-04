"""
Inventory service - Quan ly ton kho va dat hang (MCP Inventory).

Cung cap cac ham:
  - check_inventory:            Kiem tra so luong ton kho.
  - place_order:                Tao don dat hang.
  - save_customer_info_to_order: Cap nhat thong tin khach vao don pending.
  - get_all_stock:              Xem ton kho toan bo.
  - get_pending_orders:         Xem danh sach don hang.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Optional

from sqlalchemy import text

from app.db import get_engine

logger = logging.getLogger("inventory")


# ------------------------------------------------------------------
# INVENTORY
# ------------------------------------------------------------------
def check_inventory(product_id: int) -> dict:
    """Kiem tra ton kho cua san pham theo ID."""
    engine = get_engine()
    with engine.connect() as conn:
        row = conn.execute(
            text("SELECT id, name, brand, price, stock FROM products WHERE id = :pid"),
            {"pid": product_id},
        ).fetchone()

    if not row:
        return {"error": f"Khong tim thay san pham co ID = {product_id}"}

    stock = int(row.stock)
    if stock == 0:
        status = "out_of_stock"
    elif stock <= 5:
        status = "low_stock"
    else:
        status = "in_stock"

    return {
        "product_id": row.id,
        "name": row.name,
        "brand": row.brand,
        "price": float(row.price),
        "stock": stock,
        "status": status,
    }


def place_order(
    product_id: int,
    quantity: int,
    customer_name: Optional[str] = None,
    customer_phone: Optional[str] = None,
) -> dict:
    """Dat hang san pham.

    - Neu du hang: tru stock, tao don thanh cong.
    - Neu khong du: tao don pending + restock request.
    """
    if quantity <= 0:
        return {"error": "So luong dat hang phai lon hon 0."}

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # engine.begin(): mot transaction, tu commit khi xong, rollback khi loi.
    # FOR UPDATE khoa dong san pham: hai don dat cung luc phai doi nhau,
    # nen khong the cung doc stock cu roi cung tru (ban vuot ton kho).
    with get_engine().begin() as conn:
        row = conn.execute(
            text(
                "SELECT id, name, brand, stock FROM products "
                "WHERE id = :pid FOR UPDATE"
            ),
            {"pid": product_id},
        ).fetchone()

        if not row:
            return {"error": f"Khong tim thay san pham co ID = {product_id}"}

        current_stock = int(row.stock)
        product_name = row.name

        if current_stock >= quantity:
            new_stock = current_stock - quantity
            conn.execute(
                text("UPDATE products SET stock = :s WHERE id = :pid"),
                {"s": new_stock, "pid": product_id},
            )
            conn.execute(
                text(
                    "INSERT INTO orders "
                    "(product_id, product_name, quantity, customer_name, "
                    "customer_phone, status, note, created_at) "
                    "VALUES (:pid, :pname, :qty, :cname, :cphone, :st, :note, :ts)"
                ),
                {
                    "pid": product_id,
                    "pname": product_name,
                    "qty": quantity,
                    "cname": customer_name,
                    "cphone": customer_phone,
                    "st": "confirmed",
                    "note": f"Da tru kho: {current_stock} -> {new_stock}",
                    "ts": now,
                },
            )

            logger.info(
                f"[Order OK] {product_name} x{quantity}, "
                f"stock: {current_stock} -> {new_stock}"
            )

            return {
                "status": "confirmed",
                "product_name": product_name,
                "quantity": quantity,
                "remaining_stock": new_stock,
                "message": (
                    f"Dat hang thanh cong! {quantity} chiec {product_name}. "
                    f"Con lai trong kho: {new_stock} chiec."
                ),
            }
        else:
            conn.execute(
                text(
                    "INSERT INTO orders "
                    "(product_id, product_name, quantity, customer_name, "
                    "customer_phone, status, note, created_at) "
                    "VALUES (:pid, :pname, :qty, :cname, :cphone, :st, :note, :ts)"
                ),
                {
                    "pid": product_id,
                    "pname": product_name,
                    "qty": quantity,
                    "cname": customer_name,
                    "cphone": customer_phone,
                    "st": "pending_restock",
                    "note": (
                        f"Yeu cau {quantity} nhung kho chi con {current_stock}. "
                        f"Thieu {quantity - current_stock} chiec. Da bao nhan vien restock."
                    ),
                    "ts": now,
                },
            )

            logger.info(
                f"[Order PENDING] {product_name} x{quantity}, "
                f"stock chi con {current_stock}, thieu {quantity - current_stock}"
            )

            result = {
                "status": "pending_restock",
                "product_name": product_name,
                "quantity_requested": quantity,
                "current_stock": current_stock,
                "shortage": quantity - current_stock,
                "message": (
                    f"So luong hien tai trong kho khong du! "
                    f"Ban yeu cau {quantity} chiec {product_name} nhung "
                    f"kho chi con {current_stock} chiec (thieu {quantity - current_stock}). "
                    f"Toi da bao cho nhan vien de restock."
                ),
            }

            if not customer_name or not customer_phone:
                result["need_customer_info"] = True
                result["message"] += (
                    " Mong ban vui long de lai HO TEN va SO DIEN THOAI "
                    "de nhan vien san sang goi lai cho ban khi hang ve."
                )

            return result


def save_customer_info_to_order(
    product_id: int,
    customer_name: str,
    customer_phone: str,
) -> dict:
    """Cap nhat thong tin khach hang vao don pending gan nhat."""
    engine = get_engine()

    with engine.connect() as conn:
        row = conn.execute(
            text(
                "SELECT id FROM orders "
                "WHERE product_id = :pid AND status = 'pending_restock' "
                "AND (customer_name IS NULL OR customer_name = '') "
                "ORDER BY created_at DESC LIMIT 1"
            ),
            {"pid": product_id},
        ).fetchone()

        if not row:
            return {
                "status": "no_pending_order",
                "message": "Khong co don hang nao can cap nhat.",
            }

        conn.execute(
            text(
                "UPDATE orders SET customer_name = :cname, customer_phone = :cphone "
                "WHERE id = :oid"
            ),
            {"cname": customer_name, "cphone": customer_phone, "oid": row.id},
        )
        conn.commit()

    return {
        "status": "updated",
        "message": (
            f"Da luu thong tin: {customer_name} - {customer_phone}. "
            f"Nhan vien se lien he voi ban som nhat khi hang ve!"
        ),
    }


def update_stock(product_id: int, new_stock: int) -> dict:
    """Cap nhat so luong ton kho cua san pham (nhan vien kho dung)."""
    if new_stock < 0:
        return {"error": "So luong ton kho khong the am."}

    with get_engine().begin() as conn:
        row = conn.execute(
            text("SELECT id, name, stock FROM products WHERE id = :pid FOR UPDATE"),
            {"pid": product_id},
        ).fetchone()

        if not row:
            return {"error": f"Khong tim thay san pham co ID = {product_id}"}

        old_stock = int(row.stock)
        conn.execute(
            text("UPDATE products SET stock = :s WHERE id = :pid"),
            {"s": new_stock, "pid": product_id},
        )

    logger.info(f"[Stock Update] {row.name}: {old_stock} -> {new_stock}")

    return {
        "product_id": product_id,
        "name": row.name,
        "old_stock": old_stock,
        "new_stock": new_stock,
        "message": f"Da cap nhat {row.name}: {old_stock} -> {new_stock} chiec.",
    }


def get_all_stock() -> list[dict]:
    """Xem ton kho toan bo san pham."""
    engine = get_engine()
    with engine.connect() as conn:
        rows = conn.execute(
            text("SELECT id, name, brand, price, stock FROM products ORDER BY id")
        ).fetchall()

    return [
        {
            "product_id": r.id,
            "name": r.name,
            "brand": r.brand,
            "price": float(r.price),
            "stock": int(r.stock),
        }
        for r in rows
    ]


def get_pending_orders() -> list[dict]:
    """Lay danh sach don hang (cho nhan vien/admin xem)."""
    engine = get_engine()
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT id, product_id, product_name, quantity, "
                "customer_name, customer_phone, status, note, created_at "
                "FROM orders ORDER BY created_at DESC"
            )
        ).fetchall()

    return [
        {
            "id": r.id,
            "product_id": r.product_id,
            "product_name": r.product_name,
            "quantity": r.quantity,
            "customer_name": r.customer_name,
            "customer_phone": r.customer_phone,
            "status": r.status,
            "note": r.note,
            "created_at": r.created_at,
        }
        for r in rows
    ]
