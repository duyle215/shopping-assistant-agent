"""
Tool definitions va dispatch cho Agent (OpenAI function-calling format).

Module nay chua:
  - 9 tool definitions (search, detail, compare, 2 handoff, inventory, order, HITL, save_info)
  - 7 _exec_* dispatcher functions
  - TOOL_DISPATCH map
  - TOOL_DEFS dict (ten -> definition, dung trong prompts.build_agent_configs)
"""

from __future__ import annotations

import json
from typing import Any

from app.services.compare import ASPECT_KEYS, compare_products
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
SEARCH_FILTERS = (
    "brand",
    "os",
    "price_min",
    "price_max",
    "ram_min",
    "battery_min",
    "storage_min",
)


def _exec_search(args: dict) -> str:
    """Goi search_products va serialize ket qua."""
    filters = {k: args[k] for k in SEARCH_FILTERS if args.get(k) not in (None, "")}
    top_k = int(args.get("top_k") or 5)
    results = search_products(query=args["query"], top_k=top_k, **filters)

    if results:
        return json.dumps([r.model_dump() for r in results], ensure_ascii=False)

    if filters:
        # Khong may nao thoa dieu kien: noi ro, kem vai goi y gan nhat (danh dau rieng)
        nearest = search_products(query=args["query"], top_k=3)
        return json.dumps(
            {
                "message": "Khong co san pham nao thoa tat ca dieu kien loc.",
                "filters": filters,
                "nearest_without_filters": [r.model_dump() for r in nearest],
            },
            ensure_ascii=False,
        )
    return json.dumps(
        {"message": "Khong tim thay san pham phu hop trong kho hang."},
        ensure_ascii=False,
    )


def _exec_compare(args: dict) -> str:
    """Goi compare_products (bang so sanh dung bang code)."""
    result = compare_products(
        product_ids=[int(i) for i in args.get("product_ids") or []],
        aspects=args.get("aspects") or None,
    )
    return json.dumps(result, ensure_ascii=False)


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
    "compare_products": _exec_compare,
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
            "Tim kiem dien thoai trong kho hang. LUON GOI tool nay khi khach hoi ve "
            "san pham, thuong hieu, tinh nang, gia ca hoac goi y. Bien nhu cau cua "
            "khach thanh bo loc: 'duoi 10 trieu' -> price_max=10000000; 'pin trau' -> "
            "battery_min=5000; 'RAM tu 12GB' -> ram_min=12; 'Samsung' -> brand. "
            "Phan nhu cau khong loc duoc (chup dem, choi game, mong nhe...) dua vao query."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Nhu cau bang loi (ten may, tinh nang, muc dich su dung)",
                },
                "brand": {
                    "type": "string",
                    "description": "Hang: Apple, Samsung, Xiaomi, OPPO, vivo, Google, realme, Honor, Nothing, ASUS",
                },
                "os": {"type": "string", "enum": ["iOS", "Android"]},
                "price_min": {"type": "number", "description": "Gia toi thieu (VND)"},
                "price_max": {"type": "number", "description": "Gia toi da (VND)"},
                "ram_min": {"type": "integer", "description": "RAM toi thieu (GB)"},
                "battery_min": {"type": "integer", "description": "Pin toi thieu (mAh)"},
                "storage_min": {"type": "integer", "description": "Bo nho trong toi thieu (GB)"},
                "top_k": {"type": "integer", "description": "So ket qua (mac dinh 5)"},
            },
            "required": ["query"],
        },
    },
}

COMPARE_TOOL_DEF = {
    "type": "function",
    "function": {
        "name": "compare_products",
        "description": (
            "So sanh 2-4 dien thoai theo product_id. Tra ve bang so sanh Markdown dung "
            "bang code tu CSDL (table_markdown) va tieu chi moi may hon (wins). "
            "Lay product_id bang search_products truoc."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "product_ids": {
                    "type": "array",
                    "items": {"type": "integer"},
                    "description": "2 den 4 product_id can so sanh",
                },
                "aspects": {
                    "type": "array",
                    "items": {"type": "string", "enum": ASPECT_KEYS},
                    "description": "Chi so cac tieu chi nay (bo trong = tat ca). Gia luon co.",
                },
            },
            "required": ["product_ids"],
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
    "compare_products": COMPARE_TOOL_DEF,
    "transfer_to_compare_agent": HANDOFF_TO_COMPARE_DEF,
    "transfer_to_sales_agent": HANDOFF_TO_SALES_DEF,
    "check_inventory": CHECK_INVENTORY_DEF,
    "place_order": PLACE_ORDER_DEF,
    "request_human_support": REQUEST_HUMAN_SUPPORT_DEF,
    "save_customer_info": SAVE_CUSTOMER_INFO_DEF,
}
