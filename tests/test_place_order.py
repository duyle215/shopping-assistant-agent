"""place_order qua Odoo: xac nhan don va giu hang, khong ban vuot ton kho khi nhieu nguoi dat cung luc."""

from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor

import pytest

from app.odoo import OdooError, get_odoo
from app.services.inventory import check_inventory, place_order, save_customer_info_to_order


def _buy(pid, qty=1, name="An", phone="0901234567", session="s1"):
    return place_order(pid, qty, customer_name=name, customer_phone=phone, session_id=session)


def _order(odoo, ref):
    return odoo.search_read(
        "sale.order", [("name", "=", ref)], ["state", "partner_id", "chat_session_id", "chat_shortage", "amount_total"]
    )[0]


def test_order_is_confirmed_and_reserves_stock(odoo, add_phone):
    pid = add_phone("Test Phone", stock=3, price=1_000_000)

    result = _buy(pid, qty=2)

    assert result["status"] == "confirmed"
    assert result["remaining_stock"] == 1
    assert check_inventory(pid)["stock"] == 1
    order = _order(odoo, result["order_ref"])
    assert order["state"] == "sale"
    assert order["chat_session_id"] == "s1"
    assert order["amount_total"] == 2_000_000
    assert order["partner_id"][1] == "An"


def test_order_larger_than_stock_stays_a_quotation(odoo, add_phone):
    pid = add_phone("Test Phone", stock=1)

    result = _buy(pid, qty=3)

    assert result["status"] == "pending_restock"
    assert result["shortage"] == 2
    assert check_inventory(pid)["stock"] == 1
    order = _order(odoo, result["order_ref"])
    assert (order["state"], order["chat_shortage"]) == ("draft", 2)


def test_contact_can_be_changed_on_waiting_quotation(odoo, add_phone):
    pid = add_phone("Test Phone", stock=0)
    ref = _buy(pid, qty=1, session="s-contact")["order_ref"]

    assert save_customer_info_to_order("s-contact", "Binh", "0912 000 111")["status"] == "updated"
    assert _order(odoo, ref)["partner_id"][1] == "Binh"
    assert save_customer_info_to_order("other-session", "X", "1")["status"] == "no_pending_order"


def test_same_phone_reuses_the_customer(odoo, add_phone):
    pid = add_phone("Test Phone", stock=5)
    a = _order(odoo, _buy(pid, phone="0987 654 321")["order_ref"])
    b = _order(odoo, _buy(pid, phone="0987654321")["order_ref"])
    assert a["partner_id"][0] == b["partner_id"][0]


def test_rejects_bad_input(odoo, add_phone):
    pid = add_phone("Test Phone", stock=1)

    assert "error" in _buy(pid, qty=0)
    assert "error" in place_order(pid, 1, customer_name="", customer_phone="0901")
    assert "error" in _buy(999_999)
    assert check_inventory(pid)["stock"] == 1


def test_chatbot_user_cannot_edit_products(odoo, add_phone):
    pid = add_phone("Test Phone", stock=1)
    with pytest.raises(OdooError):
        get_odoo().write("product.template", [pid], {"list_price": 1})


def test_concurrent_buyers_cannot_oversell_last_unit(odoo, add_phone):
    """Nhieu khach bam dat cung luc mon cuoi cung: chi dung 1 don duoc xac nhan."""
    buyers = 8
    rounds = 3

    for round_no in range(rounds):
        pid = add_phone(f"Last Unit {round_no}", stock=1)
        start = threading.Barrier(buyers)

        def buy(i):
            start.wait()
            return _buy(pid, name=f"Buyer {i}", phone=f"09000000{i:02d}", session=f"c{i}")

        with ThreadPoolExecutor(max_workers=buyers) as pool:
            results = list(pool.map(buy, range(buyers)))

        statuses = [r.get("status") or r.get("error") for r in results]
        assert statuses.count("confirmed") == 1, statuses
        assert statuses.count("pending_restock") == buyers - 1, statuses
        assert check_inventory(pid)["stock"] == 0
