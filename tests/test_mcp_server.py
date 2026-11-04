"""MCP server: danh sach tool, annotation, va goi tool that tren database test."""

from __future__ import annotations

import json

import anyio
from sqlalchemy import text

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


def test_place_order_and_inventory_through_mcp(db):
    with db.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO products (id, name, brand, model, price, stock, chipset, ram_gb, "
                "storage_gb, screen_inch, refresh_rate_hz, battery_mah, main_camera_mp, os) "
                "VALUES (1, 'Phone A', 'Brand', 'A', 5000000, 3, 'Chip', 8, '{128}', 6.5, 120, "
                "5000, 50, 'Android')"
            )
        )

    assert _call("check_inventory", {"product_id": 1})["stock"] == 3
    order = _call("place_order", {"product_id": 1, "quantity": 2, "customer_name": "An"})
    assert order["status"] == "confirmed"
    assert _call("check_inventory", {"product_id": 1})["stock"] == 1
    assert _call("get_product", {"product_id": 1})["name"] == "Phone A"
