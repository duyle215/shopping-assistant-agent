"""
Tool definitions va dispatch cho Agent (OpenAI function-calling format).

Module nay chua:
  - 8 tool definitions (search, detail, 2 handoff, inventory, order, HITL, save_info)
  - 6 _exec_* dispatcher functions
  - TOOL_DISPATCH map
  - TOOL_DEFS dict (ten -> definition, dung trong prompts.build_agent_configs)
"""

from __future__ import annotations

import json
from typing import Any

from app.services.search import search_products
from app.services.product import get_product_details
from app.services.inventory import (
    check_inventory,
    place_order,
    save_customer_info_to_order,
)
from app.services.support import (
    request_human_support,
    save_customer_info_to_support,
)


# ------------------------------------------------------------------
# TOOL DISPATCH FUNCTIONS
# ------------------------------------------------------------------
def _exec_search(args: dict) -> str:
    """Goi search_products va serialize ket qua."""
    results = search_products(
        query=args["query"],
        brand_filter=args.get("brand_filter"),
        max_price=args.get("max_price"),
        top_k=args.get("top_k", 3),
    )
    # Retry khong filter neu 0 ket qua
    if not results and (args.get("brand_filter") or args.get("max_price")):
        results = search_products(query=args["query"])

    if not results:
        return json.dumps(
            {"message": "Khong tim thay san pham phu hop trong kho hang."},
            ensure_ascii=False,
        )
    return json.dumps(
        [r.model_dump() for r in results],
        ensure_ascii=False,
    )


def _exec_detail(args: dict) -> str:
    """Goi get_product_details va serialize ket qua."""
    detail = get_product_details(args["product_id"])
    if detail:
        return json.dumps(detail.model_dump(), ensure_ascii=False)
    return json.dumps(
        {"error": f"Khong tim thay san pham co ID = {args['product_id']}"},
        ensure_ascii=False,
    )


def _exec_check_inventory(args: dict) -> str:
    """Goi check_inventory va serialize ket qua."""
    result = check_inventory(args["product_id"])
    return json.dumps(result, ensure_ascii=False)


def _exec_place_order(args: dict) -> str:
    """Goi place_order va serialize ket qua."""
    result = place_order(
        product_id=args["product_id"],
        quantity=args["quantity"],
        customer_name=args.get("customer_name"),
        customer_phone=args.get("customer_phone"),
    )
    return json.dumps(result, ensure_ascii=False)


def _exec_request_human(args: dict) -> str:
    """Goi request_human_support va serialize ket qua."""
    result = request_human_support(
        reason=args["reason"],
        session_id=args.get("session_id"),
        customer_name=args.get("customer_name"),
        customer_phone=args.get("customer_phone"),
    )
    return json.dumps(result, ensure_ascii=False)


def _exec_save_customer_info(args: dict) -> str:
    """Luu thong tin khach hang vao don hang hoac yeu cau ho tro."""
    context = args.get("context", "order")
    name = args.get("customer_name", "")
    phone = args.get("customer_phone", "")

    if context == "support":
        result = save_customer_info_to_support(
            session_id=args.get("session_id", ""),
            customer_name=name,
            customer_phone=phone,
        )
    else:
        result = save_customer_info_to_order(
            product_id=args.get("product_id", 0),
            customer_name=name,
            customer_phone=phone,
        )
    return json.dumps(result, ensure_ascii=False)


# ------------------------------------------------------------------
# TOOL DISPATCH MAP
# ------------------------------------------------------------------
TOOL_DISPATCH: dict[str, Any] = {
    "search_products": _exec_search,
    "get_product_details": _exec_detail,
    "check_inventory": _exec_check_inventory,
    "place_order": _exec_place_order,
    "request_human_support": _exec_request_human,
    "save_customer_info": _exec_save_customer_info,
}


# ------------------------------------------------------------------
# TOOL DEFINITIONS (OpenAI function-calling format)
# ------------------------------------------------------------------
SEARCH_TOOL_DEF = {
    "type": "function",
    "function": {
        "name": "search_products",
        "description": (
            "Tim kiem san pham dien thoai trong kho hang. "
            "LUON GOI tool nay khi khach hoi ve san pham, thuong hieu, "
            "tinh nang, gia ca, goi y, hoac bat ky noi dung lien quan san pham."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Noi dung tim kiem (ten, tinh nang, nhu cau)",
                },
                "brand_filter": {
                    "type": "string",
                    "description": "Loc theo thuong hieu: Apple, Samsung, Xiaomi, OPPO, Google",
                },
                "max_price": {
                    "type": "number",
                    "description": "Gia toi da (VND)",
                },
            },
            "required": ["query"],
        },
    },
}

DETAIL_TOOL_DEF = {
    "type": "function",
    "function": {
        "name": "get_product_details",
        "description": (
            "Lay thong so ky thuat day du cua san pham theo ID. "
            "Dung khi can biet: RAM, pin, chip, camera, man hinh, ..."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "product_id": {
                    "type": "integer",
                    "description": "ID cua san pham",
                }
            },
            "required": ["product_id"],
        },
    },
}

HANDOFF_TO_COMPARE_DEF = {
    "type": "function",
    "function": {
        "name": "transfer_to_compare_agent",
        "description": (
            "Chuyen sang chuyen gia so sanh khi khach hang muon "
            "so sanh 2 hoac nhieu san pham voi nhau."
        ),
        "parameters": {"type": "object", "properties": {}},
    },
}

HANDOFF_TO_SALES_DEF = {
    "type": "function",
    "function": {
        "name": "transfer_to_sales_agent",
        "description": (
            "Chuyen lai cho tu van vien ban hang khi da hoan thanh "
            "so sanh hoac khach co cau hoi khac."
        ),
        "parameters": {"type": "object", "properties": {}},
    },
}

CHECK_INVENTORY_DEF = {
    "type": "function",
    "function": {
        "name": "check_inventory",
        "description": (
            "Kiem tra so luong ton kho cua san pham theo product_id. "
            "Goi khi khach hoi con hang khong, so luong bao nhieu, "
            "hoac truoc khi dat hang."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "product_id": {
                    "type": "integer",
                    "description": "ID cua san pham can kiem tra ton kho",
                }
            },
            "required": ["product_id"],
        },
    },
}

PLACE_ORDER_DEF = {
    "type": "function",
    "function": {
        "name": "place_order",
        "description": (
            "Dat hang san pham. Neu kho du hang se tru stock va xac nhan. "
            "Neu khong du hang se tao don cho restock va yeu cau khach "
            "de lai thong tin lien he."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "product_id": {
                    "type": "integer",
                    "description": "ID san pham muon mua",
                },
                "quantity": {
                    "type": "integer",
                    "description": "So luong muon mua",
                },
                "customer_name": {
                    "type": "string",
                    "description": "Ho ten khach hang (neu co)",
                },
                "customer_phone": {
                    "type": "string",
                    "description": "So dien thoai khach hang (neu co)",
                },
            },
            "required": ["product_id", "quantity"],
        },
    },
}

REQUEST_HUMAN_SUPPORT_DEF = {
    "type": "function",
    "function": {
        "name": "request_human_support",
        "description": (
            "Yeu cau nhan vien ho tro khach hang. GOI tool nay khi:\n"
            "1. Khach muon duoc nhan vien tu van them sau khi so sanh.\n"
            "2. Cau hoi NGOAI pham vi CSDL san pham (bao hanh, doi tra, "
            "chuong trinh khuyen mai, thanh toan, giao hang, v.v.) "
            "- TUYET DOI KHONG tu suy dien cau tra loi.\n"
            "3. Khach yeu cau noi chuyen voi nguoi that.\n"
            "Luon de nghi khach cung cap ho ten va so dien thoai."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "reason": {
                    "type": "string",
                    "description": "Ly do can ho tro nhan vien",
                },
                "session_id": {
                    "type": "string",
                    "description": "Session ID cua cuoc hoi thoai",
                },
                "customer_name": {
                    "type": "string",
                    "description": "Ho ten khach hang (neu da biet)",
                },
                "customer_phone": {
                    "type": "string",
                    "description": "So dien thoai khach hang (neu da biet)",
                },
            },
            "required": ["reason"],
        },
    },
}

SAVE_CUSTOMER_INFO_DEF = {
    "type": "function",
    "function": {
        "name": "save_customer_info",
        "description": (
            "Luu thong tin khach hang (ho ten, so dien thoai) vao don hang "
            "hoac yeu cau ho tro. Goi khi khach cung cap thong tin lien he."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "customer_name": {
                    "type": "string",
                    "description": "Ho ten khach hang",
                },
                "customer_phone": {
                    "type": "string",
                    "description": "So dien thoai khach hang",
                },
                "context": {
                    "type": "string",
                    "enum": ["order", "support"],
                    "description": "Ngu canh: 'order' (don hang) hoac 'support' (yeu cau ho tro)",
                },
                "product_id": {
                    "type": "integer",
                    "description": "ID san pham (chi can khi context='order')",
                },
                "session_id": {
                    "type": "string",
                    "description": "Session ID (chi can khi context='support')",
                },
            },
            "required": ["customer_name", "customer_phone", "context"],
        },
    },
}


# Dict ten -> definition, dung cho prompts.build_agent_configs()
TOOL_DEFS: dict[str, dict] = {
    "search_products": SEARCH_TOOL_DEF,
    "get_product_details": DETAIL_TOOL_DEF,
    "transfer_to_compare_agent": HANDOFF_TO_COMPARE_DEF,
    "transfer_to_sales_agent": HANDOFF_TO_SALES_DEF,
    "check_inventory": CHECK_INVENTORY_DEF,
    "place_order": PLACE_ORDER_DEF,
    "request_human_support": REQUEST_HUMAN_SUPPORT_DEF,
    "save_customer_info": SAVE_CUSTOMER_INFO_DEF,
}
