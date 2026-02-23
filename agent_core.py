"""
Phase 3 - Shopping Agent Core
Luan AI Agent cho cua hang dien thoai.

Luong hoat dong:
  Buoc 1  (Intent Parsing)  - phan tich y dinh nguoi dung       [INTENT_MODEL]
  Buoc 2  (Tool Execution)  - goi search_products / get_details  [Qdrant / Postgres]
  Buoc 3  (Synthesis)       - tong hop va tra loi dang Markdown  [SYNTHESIS_MODEL]

Cau hinh dua vao .env, tuong thich ca Ollama va OpenAI that.
"""

from __future__ import annotations

import json
import os
import sys
from typing import Any, Optional

from dotenv import load_dotenv
from openai import OpenAI
from pydantic import BaseModel, Field

load_dotenv()


# ------------------------------------------------------------------
# 0. CONFIG
# ------------------------------------------------------------------
def _require(key: str) -> str:
    val = os.getenv(key)
    if not val:
        sys.exit(f"[ERROR] Thieu bien '{key}' trong file .env")
    return val


# Client cho embedding (OpenAI hoac Ollama)
EMBED_BASE_URL = _require("OPENAI_BASE_URL")
EMBED_API_KEY = _require("OPENAI_API_KEY")
EMBED_MODEL = _require("EMBED_MODEL")
EMBED_DIM = int(_require("EMBED_DIM"))

# Client cho Agent reasoning - Intent (Ollama local)
AGENT_BASE_URL = _require("AGENT_BASE_URL")
AGENT_API_KEY = _require("AGENT_API_KEY")
INTENT_MODEL = _require("INTENT_MODEL")

# Client cho Synthesis (mac dinh dung OpenAI de chat luong tot hon)
SYNTHESIS_MODEL = _require("SYNTHESIS_MODEL")
SYNTH_BASE_URL = os.getenv("SYNTHESIS_BASE_URL") or EMBED_BASE_URL
SYNTH_API_KEY = os.getenv("SYNTHESIS_API_KEY") or EMBED_API_KEY

# LLM model (dung chung cho cac tac vu khac neu can)
LLM_MODEL = os.getenv("LLM_MODEL", SYNTHESIS_MODEL)

# Postgres
PG_HOST = _require("POSTGRES_HOST")
PG_PORT = _require("POSTGRES_PORT")
PG_DB = _require("POSTGRES_DB")
PG_USER = _require("POSTGRES_USER")
PG_PASSWORD = _require("POSTGRES_PASSWORD")

# Qdrant
QDRANT_PATH = _require("QDRANT_PATH")
QDRANT_COLLECTION = _require("QDRANT_COLLECTION")

PG_URL = (
    f"postgresql+psycopg2://{PG_USER}:{PG_PASSWORD}" f"@{PG_HOST}:{PG_PORT}/{PG_DB}"
)


# ------------------------------------------------------------------
# 1. PYDANTIC SCHEMAS
# ------------------------------------------------------------------
class IntentResult(BaseModel):
    """Ket qua phan tich y dinh nguoi dung."""

    intent: str = Field(
        description=(
            "Mot trong: 'search' (tim san pham), "
            "'get_details' (hoi chi tiet 1 san pham), "
            "'compare' (so sanh san pham), "
            "'general' (cau hoi chung)"
        )
    )
    query: Optional[str] = Field(
        None, description="Tu khoa tim kiem neu intent la search/compare"
    )
    product_id: Optional[int] = Field(
        None, description="ID san pham neu intent la get_details"
    )
    brand_filter: Optional[str] = Field(None, description="Thuong hieu muon loc neu co")
    max_price: Optional[float] = Field(
        None, description="Gia toi da (VND) neu nguoi dung neu ra"
    )
    reasoning: str = Field(
        default="", description="Giai thich ngan ly do ban phan tich vay"
    )


class ProductMetadata(BaseModel):
    """Thong tin san pham tra ve tu Postgres."""

    id: int
    name: str
    brand: str
    price: float
    specs: dict[str, Any]
    description: str


class SearchResult(BaseModel):
    """Mot ket qua tim kiem tu Qdrant."""

    product_id: int
    name: str
    brand: str
    price: float
    score: float
    description: str


class AgentResponse(BaseModel):
    """Response cuoi cung tra ve cho frontend."""

    intent: str
    answer_markdown: str
    tools_called: list[str]
    warning: Optional[str] = None


# ------------------------------------------------------------------
# 2. TOOL FUNCTIONS
# ------------------------------------------------------------------
# Map thuong hieu (case-insensitive) -> ten chinh xac trong CSDL
BRAND_NORMALIZE_MAP: dict[str, str] = {
    "apple": "Apple",
    "iphone": "Apple",
    "samsung": "Samsung",
    "galaxy": "Samsung",
    "xiaomi": "Xiaomi",
    "mi": "Xiaomi",
    "redmi": "Xiaomi",
    "oppo": "OPPO",
    "google": "Google",
    "pixel": "Google",
}


def _normalize_brand(raw: Optional[str]) -> Optional[str]:
    """Chuan hoa ten thuong hieu cho khop voi du lieu Qdrant."""
    if not raw:
        return None
    key = raw.strip().lower()
    return BRAND_NORMALIZE_MAP.get(key, raw)


def search_products(
    query: str,
    brand_filter: Optional[str] = None,
    max_price: Optional[float] = None,
    top_k: int = 3,
) -> list[SearchResult]:
    """
    Tim san pham trong Qdrant bang semantic search,
    ket hop filter metadata (brand, price).
    """
    from openai import OpenAI as OAIClient
    from qdrant_client import QdrantClient
    from qdrant_client.models import FieldCondition, Filter, MatchValue, Range

    # Chuan hoa brand filter truoc khi query (fix loi case-sensitive)
    brand_filter = _normalize_brand(brand_filter)

    # Tao vector tu query
    embed_client = OAIClient(base_url=EMBED_BASE_URL, api_key=EMBED_API_KEY)
    resp = embed_client.embeddings.create(model=EMBED_MODEL, input=query)
    query_vector = resp.data[0].embedding

    # Build filter
    conditions = []
    if brand_filter:
        conditions.append(
            FieldCondition(key="brand", match=MatchValue(value=brand_filter))
        )
    if max_price:
        conditions.append(FieldCondition(key="price", range=Range(lte=max_price)))

    qdrant_filter = Filter(must=conditions) if conditions else None

    qdrant = QdrantClient(path=QDRANT_PATH)
    hits = qdrant.query_points(
        collection_name=QDRANT_COLLECTION,
        query=query_vector,
        query_filter=qdrant_filter,
        limit=top_k,
        with_payload=True,
    ).points

    results = []
    for hit in hits:
        p = hit.payload
        results.append(
            SearchResult(
                product_id=p["product_id"],
                name=p["name"],
                brand=p["brand"],
                price=p["price"],
                score=round(hit.score, 4),
                description=p["description"],
            )
        )
    return results


def get_product_details(product_id: int) -> Optional[ProductMetadata]:
    """
    Lay thong so ky thuat chi tiet tu Postgres bang product_id.
    """
    from sqlalchemy import create_engine, text

    engine = create_engine(PG_URL, echo=False)
    with engine.connect() as conn:
        row = conn.execute(
            text(
                "SELECT id, name, brand, price, specs, description FROM products WHERE id = :pid"
            ),
            {"pid": product_id},
        ).fetchone()

    if not row:
        return None

    return ProductMetadata(
        id=row.id,
        name=row.name,
        brand=row.brand,
        price=float(row.price),
        specs=json.loads(row.specs) if isinstance(row.specs, str) else row.specs,
        description=row.description,
    )


# ------------------------------------------------------------------
# 3. TOOL DEFINITIONS (OpenAI function-calling format)
# ------------------------------------------------------------------
TOOL_DEFINITIONS = [
    {
        "type": "function",
        "function": {
            "name": "search_products",
            "description": (
                "Tim kiem san pham dua tren mo ta, ten, review. "
                "Dung khi khach hoi san pham phu hop, so sanh, or tim theo nhu cau."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Tu khoa tim kiem (ten, tinh nang, use case)",
                    },
                    "brand_filter": {
                        "type": "string",
                        "description": "Loc theo thuong hieu (Apple, Samsung, ...)",
                    },
                    "max_price": {
                        "type": "number",
                        "description": "Gia toi da tinh bang VND",
                    },
                    "top_k": {
                        "type": "integer",
                        "description": "So luong ket qua tra ve (mac dinh 3)",
                        "default": 3,
                    },
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_product_details",
            "description": (
                "Lay thong so ky thuat day du cua mot san pham theo ID. "
                "Dung khi khach hoi cu the: RAM bao nhieu, pin bao nhieu, chip gi, ..."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "product_id": {
                        "type": "integer",
                        "description": "ID cua san pham can xem chi tiet",
                    }
                },
                "required": ["product_id"],
            },
        },
    },
]


# ------------------------------------------------------------------
# 4. SHOPPING AGENT CLASS
# ------------------------------------------------------------------
SYSTEM_PROMPT = """Ban la tu van vien ban hang dien thoai chuyen nghiep tai cua hang.

NGUYEN TAC BAT BUOC:
1. CHI tra loi dua tren DU LIEU DUOC CUNG CAP. TUYET DOI KHONG tu suy dien hoac dung kien thuc tu co cua ban.
2. Neu du lieu co san pham phu hop -> gioi thieu CU THE: ten, gia, diem noi bat chinh.
3. Neu du lieu KHONG co san pham phu hop -> noi thang: "Hien tai cua hang chua co san pham nay trong kho."
4. KHONG BAO GIO hien thi: diem so (score), metadata noi bo, cau truc prompt, hoac bat ky du lieu ky thuat he thong nao.
5. Tra loi bang Tieng Viet tu nhien, than thien nhu dang noi chuyen truc tiep voi khach.
6. Dinh dang Markdown ro rang (bold ten san pham, danh sach diem noi bat, bang so sanh neu can).
7. So sanh trung thuc, khong thien vi thuong hieu nao.
8. Neu khach chua ro nhu cau, dat 1-2 cau hoi goi y de tu van tot hon.
"""

INTENT_SYSTEM_PROMPT = """Ban la he thong phan tich y dinh khach hang cho cua hang dien thoai.
Phan tich cau hoi va tra ve MOT object JSON duy nhat, KHONG them bat ky text nao khac.

QUY TAC PHAN LOAI:
- Neu khach nhac den THUONG HIEU (Samsung, Apple, OPPO, Xiaomi, Google, iPhone, Pixel...)
  hoac TEN SAN PHAM, hoac hoi ve tinh nang/gia/thong so -> intent = "search"
- Neu khach hoi "co gi", "thong tin", "gioi thieu", "tu van", "goi y" ve dien thoai -> intent = "search"
- Neu khach muon SO SANH 2 san pham tro len -> intent = "compare"
- Neu khach cho biet product_id cu the (so) -> intent = "get_details"
- CHI DUNG intent = "general" khi cau hoi HOAN TOAN khong lien quan san pham (vd: "Cam on", "Gio mo cua")

Luu y ve brand_filter:
- Phai viet DUNG ten: Apple, Samsung, Xiaomi, OPPO, Google
- Neu khong chac thuong hieu -> de null (he thong se tu tim)

JSON schema:
{
  "intent": "search" | "get_details" | "compare" | "general",
  "query": "<cau hoi goc hoac tu khoa tim kiem - KHONG de null neu intent la search/compare>",
  "product_id": <id so nguyen hoac null>,
  "brand_filter": "<Apple | Samsung | Xiaomi | OPPO | Google | null>",
  "max_price": <so VND hoac null>,
  "reasoning": "<giai thich ngan>"
}"""


class ShoppingAgent:
    """
    Agent tu van mua dien thoai.

    Su dung:
        agent = ShoppingAgent()
        response = agent.run("Dien thoai Samsung pin trau duoi 20 trieu?")
        print(response.answer_markdown)
    """

    def __init__(self) -> None:
        # Client cho Intent parsing (Ollama local - nhe, nhanh)
        self.agent_client = OpenAI(
            base_url=AGENT_BASE_URL,
            api_key=AGENT_API_KEY,
        )
        # Client cho Synthesis (OpenAI gpt-4.1-mini - chat luong cao)
        self.synth_client = OpenAI(
            base_url=SYNTH_BASE_URL,
            api_key=SYNTH_API_KEY,
        )

    # ── Buoc 1: Phan tich y dinh ──────────────────────────────
    def _parse_intent(self, user_message: str) -> IntentResult:
        resp = self.agent_client.chat.completions.create(
            model=INTENT_MODEL,
            messages=[
                {"role": "system", "content": INTENT_SYSTEM_PROMPT},
                {"role": "user", "content": user_message},
            ],
            temperature=0,
        )
        raw = resp.choices[0].message.content.strip()

        # Trich xuat JSON neu model them text bao ngoai
        start = raw.find("{")
        end = raw.rfind("}") + 1
        if start == -1 or end == 0:
            # Fallback: xu ly nhu search chung
            return IntentResult(
                intent="search",
                query=user_message,
                reasoning="Khong parse duoc JSON, fallback sang search.",
            )
        return IntentResult.model_validate_json(raw[start:end])

    # -- Buoc 2: Chon va chay tool ----------------------------------------
    def _execute_tools(
        self, intent: IntentResult, user_message: str
    ) -> tuple[list[str], str]:
        """Tra ve (danh sach tool da goi, context string cho synthesis).

        LUON chay search_products truoc (RAG backbone).
        Sau do bo sung get_product_details neu can (compare, get_details).
        """
        tools_called: list[str] = []
        context_parts: list[str] = []

        # ---- LUON search truoc ----
        query = intent.query or user_message
        results = search_products(
            query=query,
            brand_filter=intent.brand_filter,
            max_price=intent.max_price,
        )
        tools_called.append("search_products")

        # Retry khong filter neu lan dau 0 ket qua (phong truong hop brand sai)
        if not results and (intent.brand_filter or intent.max_price):
            results = search_products(query=query)
            tools_called.append("search_products(retry_no_filter)")

        if not results:
            context_parts.append("Khong tim thay san pham phu hop trong kho hang.")
        else:
            lines = []
            for r in results:
                lines.append(
                    f"- {r.name} ({r.brand}) | Gia: {r.price:,.0f} VND\n"
                    f"  {r.description}"
                )
            context_parts.append(
                "San pham tim thay trong kho hang:\n" + "\n".join(lines)
            )

        # ---- Bo sung chi tiet specs neu compare hoac get_details ----
        if intent.intent in ("compare", "get_details"):
            # Neu co product_id cu the -> lay chi tiet san pham do
            if intent.product_id:
                detail = get_product_details(intent.product_id)
                tools_called.append(f"get_product_details(id={intent.product_id})")
                if detail:
                    specs_str = "\n".join(
                        f"  - {k}: {v}" for k, v in detail.specs.items()
                    )
                    context_parts.append(
                        f"Thong tin day du - {detail.name} ({detail.brand}):\n"
                        f"Gia: {detail.price:,.0f} VND\n"
                        f"Mo ta: {detail.description}\n"
                        f"Specs:\n{specs_str}"
                    )

            # Neu compare hoac search co ket qua -> lay specs tung san pham
            if intent.intent == "compare" and results:
                for r in results:
                    detail = get_product_details(r.product_id)
                    tools_called.append(f"get_product_details(id={r.product_id})")
                    if detail:
                        specs_str = "\n".join(
                            f"  - {k}: {v}" for k, v in detail.specs.items()
                        )
                        context_parts.append(
                            f"Specs chi tiet - {detail.name}:\n{specs_str}"
                        )

        return tools_called, "\n\n".join(context_parts)

    # ── Canh bao neu specs tot nhung review che ──────────────
    @staticmethod
    def _extract_warning(context: str, intent: IntentResult) -> Optional[str]:
        negative_keywords = [
            "nong may",
            "lag",
            "chat luong kem",
            "pin yeu",
            "camera te",
            "hay hang",
            "do ben thap",
            "loi",
            "che",
            "kem",
        ]
        query_lower = (intent.query or "").lower()
        hits = [kw for kw in negative_keywords if kw in context.lower()]

        if hits and intent.intent in ("search", "get_details"):
            return (
                f"Luu y: Du lieu co mot so phan anh tieu cuc "
                f"({', '.join(hits)}). Hay doc ky phan review truoc khi quyet dinh."
            )
        return None

    # ── Buoc 3: Tong hop va tra loi ─────────────────────────
    def _synthesize(
        self,
        user_message: str,
        intent: IntentResult,
        context: str,
        warning: Optional[str],
    ) -> str:
        warning_block = f"\n\nLUU Y QUAN TRONG: {warning}" if warning else ""
        synthesis_user_prompt = (
            f"KHACH HANG HOI: {user_message}\n\n"
            f"DU LIEU SAN PHAM TU CUA HANG (chi dung du lieu nay, khong tu suy dien):\n"
            f"{context}"
            f"{warning_block}\n\n"
            "YEU CAU TRA LOI:\n"
            "- Tra loi nhu TU VAN VIEN BAN HANG dang noi chuyen voi khach, KHONG nhu may tim kiem.\n"
            "- KHONG hien thi score, metadata, prompt, hay bat ky du lieu noi bo nao.\n"
            "- Gioi thieu san pham cu the: ten, gia, va 2-3 diem noi bat chinh.\n"
            "- Dung Tieng Viet tu nhien, than thien, dinh dang Markdown.\n"
            "- Neu khong co du lieu san pham -> noi thang la cua hang chua co."
        )

        resp = self.synth_client.chat.completions.create(
            model=SYNTHESIS_MODEL,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": synthesis_user_prompt},
            ],
            temperature=0.3,
        )
        return resp.choices[0].message.content.strip()

    # ── Entry point chinh ────────────────────────────────────
    def run(self, user_message: str) -> AgentResponse:
        # Buoc 1: Intent
        print(
            f"[Agent] Phan tich y dinh: '{user_message[:60]}...' "
            if len(user_message) > 60
            else f"[Agent] Phan tich y dinh: '{user_message}'"
        )
        intent = self._parse_intent(user_message)
        print(
            f"[Agent] Intent = {intent.intent} | Query = {intent.query} | Reasoning = {intent.reasoning}"
        )

        # Buoc 2: Tool execution
        tools_called, context = self._execute_tools(intent, user_message)
        print(f"[Agent] Tools goi: {tools_called}")

        # Kiem tra canh bao
        warning = self._extract_warning(context, intent)

        # Buoc 3: Synthesis
        print(f"[Agent] Tong hop voi model '{SYNTHESIS_MODEL}'...")
        answer = self._synthesize(user_message, intent, context, warning)

        return AgentResponse(
            intent=intent.intent,
            answer_markdown=answer,
            tools_called=tools_called,
            warning=warning,
        )


# ------------------------------------------------------------------
# 5. DEMO CLI
# ------------------------------------------------------------------
if __name__ == "__main__":
    agent = ShoppingAgent()

    test_queries = [
        "Dien thoai Samsung pin trau duoi 25 trieu la cai nao?",
        "iPhone 15 Pro Max co bao nhieu RAM va dung luong?",
        "So sanh Xiaomi 14 Ultra va OPPO Find X7 Pro cai nao chup anh dep hon?",
    ]

    for q in test_queries:
        print("\n" + "=" * 60)
        print(f"CAU HOI: {q}")
        print("=" * 60)
        result = agent.run(q)
        print("\n--- TRA LOI ---")
        print(result.answer_markdown)
        if result.warning:
            print(f"\n[CANH BAO]: {result.warning}")
        print(f"\n[Tools da goi]: {result.tools_called}")
