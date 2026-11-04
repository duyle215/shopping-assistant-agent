"""
Support service - chuyen tiep sang nhan vien (human-in-the-loop) qua CRM cua Odoo.

Moi yeu cau ho tro la mot crm.lead, gan chat_session_id de nhan vien mo lai cuoc hoi thoai
va de bo sung ten / SDT khi khach gui sau. (Helpdesk chi co o Odoo Enterprise.)
"""

from __future__ import annotations

import logging
from typing import Optional

from app.odoo import get_odoo

logger = logging.getLogger("support")

TITLE_PREFIX = "[Chatbot] "


def request_human_support(
    reason: str,
    session_id: Optional[str] = None,
    customer_name: Optional[str] = None,
    customer_phone: Optional[str] = None,
) -> dict:
    """Tao yeu cau ho tro tu nhan vien (crm.lead)."""
    title = reason.strip().splitlines()[0] if reason.strip() else "Yeu cau ho tro"
    vals = {
        "name": TITLE_PREFIX + (title[:80] + ("..." if len(title) > 80 else "")),
        "description": reason,
        "chat_session_id": session_id,
    }
    if customer_name:
        vals["contact_name"] = customer_name
    if customer_phone:
        vals["phone"] = customer_phone
    lead_id = get_odoo().create("crm.lead", vals)
    logger.info(f"[HITL] crm.lead #{lead_id}: {reason[:80]}")

    result = {
        "status": "support_requested",
        "ticket_id": lead_id,
        "reason": reason,
        "message": "Da gui yeu cau ho tro cho nhan vien.",
    }
    if not customer_name or not customer_phone:
        result["need_customer_info"] = True
        result["message"] += (
            " Vui long cung cap HO TEN va SO DIEN THOAI de nhan vien co the lien he tu van cho ban."
        )
    else:
        result["message"] += (
            f" Nhan vien se lien he voi {customer_name} qua so {customer_phone} trong thoi gian som nhat."
        )
    return result


def save_customer_info_to_support(session_id: str, customer_name: str, customer_phone: str) -> dict:
    """Cap nhat ten + SDT vao yeu cau ho tro gan nhat chua co SDT cua phien chat."""
    odoo = get_odoo()
    ids = odoo.search(
        "crm.lead",
        [("chat_session_id", "=", session_id), ("phone", "in", [False, ""])],
        order="id desc",
        limit=1,
    )
    if not ids:
        return {"status": "no_pending_request", "message": "Khong co yeu cau ho tro nao can cap nhat."}
    odoo.write("crm.lead", ids, {"contact_name": customer_name, "phone": customer_phone})
    return {
        "status": "updated",
        "message": (
            f"Da luu thong tin: {customer_name} - {customer_phone}. "
            "Nhan vien se lien he voi ban som nhat!"
        ),
    }
