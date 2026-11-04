"""MCP server: danh sach tool, annotation, va goi tool that tren Odoo test."""

from __future__ import annotations

import json

import anyio
from app.mcp_server import server


def _call(name, args):
    async def go():
        return await server.call_tool(name, args)

    result = anyio.run(go)
    assert not result.is_error, result
    return json.loads(result.content[0].text)


def _tools():
    async def go():
        return await server.list_tools()

    return {t.name: t for t in anyio.run(go)}


def test_tools_are_listed_with_annotations():
    tools = _tools()
    assert set(tools) == {"search_products", "get_product", "check_inventory", "compare_products", "place_order"}
    assert tools["check_inventory"].annotations.read_only_hint is True
    assert tools["place_order"].annotations.read_only_hint is False


def test_place_order_and_inventory_through_mcp(odoo, add_phone):
    pid = add_phone("Phone A", stock=3, price=5_000_000, brand="Brand", os="Android")

    assert _call("check_inventory", {"product_id": pid})["stock"] == 3
    order = _call(
        "place_order", {"product_id": pid, "quantity": 2, "customer_name": "An", "customer_phone": "0901"}
    )
    assert order["status"] == "confirmed"
    assert order["order_ref"]
    assert _call("check_inventory", {"product_id": pid})["stock"] == 1
    assert _call("get_product", {"product_id": pid})["name"] == "Phone A"
