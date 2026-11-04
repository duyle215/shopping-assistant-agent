"""
MCP server cho kho hang - cho agent hoac ung dung khac (bat ky MCP client nao) dung lai
cac nghiep vu cua cua hang: tim san pham, xem thong so, kiem tra ton kho, so sanh, dat hang.

Dung chung service voi chatbot (cung PostgreSQL / Qdrant, cung row lock khi dat hang).

Chay:
    python -m app.mcp_server                 # stdio (MCP client tu khoi dong process)
    python -m app.mcp_server --http          # streamable HTTP tai http://localhost:8000/mcp

Cau hinh MCP client (stdio), vd:
    {"command": "python", "args": ["-m", "app.mcp_server"], "cwd": "<thu muc project>"}
"""

from __future__ import annotations

import argparse
from typing import Optional

from mcp.server.mcpserver import MCPServer
from mcp.types import ToolAnnotations

server = MCPServer(
    "shopping-inventory",
    instructions=(
        "Phone shop inventory (Vietnam, prices in VND). Use search_products to find product ids, "
        "then get_product, check_inventory or compare_products. place_order changes stock: "
        "confirm with the customer before calling it."
    ),
)

READ_ONLY = ToolAnnotations(readOnlyHint=True, openWorldHint=False)


@server.tool(annotations=READ_ONLY)
def search_products(
    query: str,
    brand: Optional[str] = None,
    price_max: Optional[int] = None,
    price_min: Optional[int] = None,
    ram_min: Optional[int] = None,
    battery_min: Optional[int] = None,
    storage_min: Optional[int] = None,
    top_k: int = 5,
) -> list[dict]:
    """Find phones by need or name (hybrid search) with optional filters. Prices in VND."""
    from app.services.search import search_products as _search

    filters = dict(
        brand=brand,
        price_max=price_max,
        price_min=price_min,
        ram_min=ram_min,
        battery_min=battery_min,
        storage_min=storage_min,
    )
    results = _search(query, top_k=top_k, **{k: v for k, v in filters.items() if v is not None})
    return [r.model_dump(exclude={"score"}) for r in results]


@server.tool(annotations=READ_ONLY)
def get_product(product_id: int) -> dict:
    """Full typed spec sheet of one phone."""
    from app.services.product import get_product_details

    product = get_product_details(product_id)
    return product.model_dump() if product else {"error": f"No product with id {product_id}"}


@server.tool(annotations=READ_ONLY)
def check_inventory(product_id: int) -> dict:
    """Stock level and status (in_stock, low_stock, out_of_stock)."""
    from app.services.inventory import check_inventory as _check

    return _check(product_id)


@server.tool(annotations=READ_ONLY)
def compare_products(product_ids: list[int]) -> dict:
    """Compare 2-4 phones: Markdown table built from the database plus the winner per aspect."""
    from app.services.compare import compare_products as _compare

    return _compare(product_ids)


@server.tool(annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=False))
def place_order(
    product_id: int,
    quantity: int,
    customer_name: Optional[str] = None,
    customer_phone: Optional[str] = None,
) -> dict:
    """Place an order. Deducts stock under a row lock, or records a pending-restock order
    when stock is short. Confirm the order with the customer first."""
    from app.services.inventory import place_order as _place

    return _place(product_id, quantity, customer_name, customer_phone)


def main() -> None:
    parser = argparse.ArgumentParser(description="Shopping inventory MCP server")
    parser.add_argument("--http", action="store_true", help="Streamable HTTP thay vi stdio")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()
    if args.http:
        server.run("streamable-http", port=args.port)
    else:
        server.run("stdio")


if __name__ == "__main__":
    main()
