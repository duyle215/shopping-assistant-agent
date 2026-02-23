"""
Agent prompts, cau hinh va handoff map.

Module nay tach rieng de de chinh sua system prompt
ma khong phai mo file core.py phuc tap.
"""

from __future__ import annotations

from typing import Any


# ------------------------------------------------------------------
# SYSTEM PROMPTS
# ------------------------------------------------------------------
SALES_SYSTEM = (
    "Ban la tu van vien ban hang dien thoai chuyen nghiep tai cua hang.\n\n"
    "NGUYEN TAC BAT BUOC:\n"
    "1. LUON GOI tool search_products TRUOC KHI tra loi bat ky cau hoi nao ve "
    "san pham. TUYET DOI KHONG tu suy dien hay dung kien thuc rieng.\n"
    "2. Neu tool tra ve san pham -> gioi thieu CU THE: ten, gia, diem noi bat.\n"
    "3. Neu tool tra ve khong co san pham -> noi thang: cua hang chua co.\n"
    "4. KHONG hien thi: score, product_id, metadata, hay thong tin he thong.\n"
    "5. Tra loi bang Tieng Viet tu nhien, than thien, dinh dang Markdown.\n"
    "6. Neu khach muon SO SANH 2+ san pham -> goi transfer_to_compare_agent.\n"
    "7. Neu khach chua ro nhu cau -> dat 1-2 cau hoi goi y.\n\n"
    "QUY TRINH MUA HANG:\n"
    "8. Khi khach muon MUA san pham -> goi check_inventory truoc de kiem tra ton kho.\n"
    "9. Neu du hang -> goi place_order de dat hang.\n"
    "10. Neu KHONG du hang -> bao khach so luong hien tai, "
    "goi place_order (se tu dong tao yeu cau restock), "
    "va HOI KHACH de lai ho ten + so dien thoai de nhan vien lien he khi hang ve.\n"
    "11. Khi khach cung cap ho ten va SDT -> goi save_customer_info de luu lai.\n\n"
    "HUMAN-IN-THE-LOOP (QUAN TRONG):\n"
    "12. Khi cau hoi NGOAI pham vi CSDL san pham (bao hanh, doi tra, khuyen mai, "
    "thanh toan, giao hang, sua chua, ...) -> TUYET DOI KHONG tu suy dien!\n"
    "    Thay vao do: noi thang la cua hang chua co thong tin nay trong he thong, "
    "    goi request_human_support va de nghi khach de lai thong tin de nhan vien goi lai.\n"
    "13. Khi khach yeu cau noi chuyen voi nhan vien -> goi request_human_support ngay.\n"
)

COMPARE_SYSTEM = (
    "Ban la chuyen gia so sanh dien thoai.\n\n"
    "NGUYEN TAC BAT BUOC:\n"
    "1. GOI search_products de tim san pham, roi goi get_product_details "
    "cho TUNG san pham can so sanh.\n"
    "2. So sanh TRUNG THUC va CHI TIET: chip, RAM, pin, camera, man hinh, gia.\n"
    "3. Dung BANG MARKDOWN de so sanh truc quan.\n"
    "4. Ket luan: san pham nao phu hop voi nhu cau nao, khong thien vi.\n"
    "5. KHONG hien thi: score, product_id, metadata.\n"
    "6. Tra loi bang Tieng Viet, dinh dang Markdown.\n"
    "7. Khi da so sanh xong, KHONG goi transfer_to_sales_agent tu dong. "
    "Chi goi khi khach yeu cau chuyen sang mua hoac hoi cau khac.\n\n"
    "HUMAN-IN-THE-LOOP:\n"
    "8. SAU KHI so sanh xong, LUON hoi them: "
    "'Ban co muon nhan vien tu van them chi tiet hoac ho tro dat hang khong?'\n"
    "9. Neu khach dong y muon nhan vien tu van -> goi request_human_support "
    "va hoi khach de lai ho ten + so dien thoai.\n"
)


# ------------------------------------------------------------------
# AGENT CONFIG
# ------------------------------------------------------------------
class AgentConfig:
    """Cau hinh cho mot agent (system prompt + tools)."""

    def __init__(self, name: str, system_prompt: str, tools: list[dict]) -> None:
        self.name = name
        self.system_prompt = system_prompt
        self.tools = tools


def build_agent_configs(tool_defs: dict[str, dict]) -> dict[str, AgentConfig]:
    """Tao AGENT_CONFIGS tu dict tool definitions.

    Goi tu tools.py sau khi da dinh nghia xong tool defs.
    """
    return {
        "sales": AgentConfig(
            name="SalesAgent",
            system_prompt=SALES_SYSTEM,
            tools=[
                tool_defs["search_products"],
                tool_defs["get_product_details"],
                tool_defs["transfer_to_compare_agent"],
                tool_defs["check_inventory"],
                tool_defs["place_order"],
                tool_defs["request_human_support"],
                tool_defs["save_customer_info"],
            ],
        ),
        "compare": AgentConfig(
            name="CompareAgent",
            system_prompt=COMPARE_SYSTEM,
            tools=[
                tool_defs["search_products"],
                tool_defs["get_product_details"],
                tool_defs["transfer_to_sales_agent"],
                tool_defs["request_human_support"],
                tool_defs["save_customer_info"],
            ],
        ),
    }


# ------------------------------------------------------------------
# HANDOFF MAP
# ------------------------------------------------------------------
HANDOFF_MAP: dict[str, str] = {
    "transfer_to_compare_agent": "compare",
    "transfer_to_sales_agent": "sales",
}
