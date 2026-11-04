"""
Support service - Human-in-the-Loop (chuyen tiep sang nhan vien).

Cung cap cac ham:
  - request_human_support:         Tao yeu cau ho tro.
  - save_customer_info_to_support: Cap nhat thong tin khach.
  - get_pending_support_requests:  Xem danh sach yeu cau ho tro.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Optional

from sqlalchemy import text

from app.db import get_engine

logger = logging.getLogger("support")


# ------------------------------------------------------------------
# SUPPORT REQUEST
# ------------------------------------------------------------------
def request_human_support(
    reason: str,
    session_id: Optional[str] = None,
    customer_name: Optional[str] = None,
    customer_phone: Optional[str] = None,
) -> dict:
    """Tao yeu cau ho tro tu nhan vien."""
    engine = get_engine()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    with engine.connect() as conn:
        conn.execute(
            text(
                "INSERT INTO support_requests "
                "(session_id, reason, customer_name, customer_phone, status, created_at) "
                "VALUES (:sid, :reason, :cname, :cphone, :st, :ts)"
            ),
            {
                "sid": session_id,
                "reason": reason,
                "cname": customer_name,
                "cphone": customer_phone,
                "st": "pending",
                "ts": now,
            },
        )
        conn.commit()

    logger.info(f"[HITL] Yeu cau ho tro: {reason[:80]}...")

    result = {
        "status": "support_requested",
        "reason": reason,
        "message": "Da gui yeu cau ho tro cho nhan vien.",
    }

    if not customer_name or not customer_phone:
        result["need_customer_info"] = True
        result["message"] += (
            " Vui long cung cap HO TEN va SO DIEN THOAI "
            "de nhan vien co the lien he tu van cho ban."
        )
    else:
        result["message"] += (
            f" Nhan vien se lien he voi {customer_name} "
            f"qua so {customer_phone} trong thoi gian som nhat."
        )

    return result


def save_customer_info_to_support(
    session_id: str,
    customer_name: str,
    customer_phone: str,
) -> dict:
    """Cap nhat thong tin khach hang vao yeu cau ho tro gan nhat."""
    engine = get_engine()

    with engine.connect() as conn:
        row = conn.execute(
            text(
                "SELECT id FROM support_requests "
                "WHERE session_id = :sid AND status = 'pending' "
                "AND (customer_name IS NULL OR customer_name = '') "
                "ORDER BY created_at DESC LIMIT 1"
            ),
            {"sid": session_id},
        ).fetchone()

        if not row:
            return {
                "status": "no_pending_request",
                "message": "Khong co yeu cau ho tro nao can cap nhat.",
            }

        conn.execute(
            text(
                "UPDATE support_requests "
                "SET customer_name = :cname, customer_phone = :cphone "
                "WHERE id = :rid"
            ),
            {"cname": customer_name, "cphone": customer_phone, "rid": row.id},
        )
        conn.commit()

    return {
        "status": "updated",
        "message": (
            f"Da luu thong tin: {customer_name} - {customer_phone}. "
            f"Nhan vien se lien he voi ban som nhat!"
        ),
    }


def get_pending_support_requests() -> list[dict]:
    """Lay danh sach yeu cau ho tro (cho nhan vien/admin xem)."""
    engine = get_engine()
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT id, session_id, reason, customer_name, customer_phone, "
                "status, created_at "
                "FROM support_requests ORDER BY created_at DESC"
            )
        ).fetchall()

    return [
        {
            "id": r.id,
            "session_id": r.session_id,
            "reason": r.reason,
            "customer_name": r.customer_name,
            "customer_phone": r.customer_phone,
            "status": r.status,
            "created_at": r.created_at,
        }
        for r in rows
    ]
