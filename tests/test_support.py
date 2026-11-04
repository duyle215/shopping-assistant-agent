"""Yeu cau ho tro thanh crm.lead trong Odoo, gan phien chat; ten / SDT bo sung sau."""

from __future__ import annotations

from app.services.support import request_human_support, save_customer_info_to_support


def _leads(odoo, session):
    return odoo.search_read(
        "crm.lead", [("chat_session_id", "=", session)], ["name", "description", "contact_name", "phone"]
    )


def test_request_creates_lead_and_asks_for_contact(odoo):
    result = request_human_support("Bảo hành iPhone bao lâu?", session_id="s-support")

    assert result["need_customer_info"] is True
    [lead] = _leads(odoo, "s-support")
    assert lead["name"].startswith("[Chatbot] Bảo hành")
    assert "Bảo hành iPhone" in lead["description"]


def test_contact_is_added_to_latest_lead_of_the_session(odoo):
    request_human_support("Đổi trả", session_id="s-a")
    request_human_support("Trả góp", session_id="s-b")

    assert save_customer_info_to_support("s-a", "Chi", "0933 111 222")["status"] == "updated"
    [lead] = _leads(odoo, "s-a")
    assert (lead["contact_name"], lead["phone"]) == ("Chi", "0933 111 222")
    assert not _leads(odoo, "s-b")[0]["phone"]
    assert save_customer_info_to_support("s-none", "X", "1")["status"] == "no_pending_request"


def test_request_with_contact_does_not_ask_again(odoo):
    result = request_human_support("Giao hàng", session_id="s-c", customer_name="Dung", customer_phone="0944")
    assert "need_customer_info" not in result
    assert _leads(odoo, "s-c")[0]["contact_name"] == "Dung"
