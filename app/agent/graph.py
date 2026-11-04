"""
Agent graph (LangGraph).

    START -> start -> agent --(tool calls)--> [confirm_order] -> tools -> agent ...
                  \\        \\--(text answer)--> check --(ok)--> finish -> END
                   \\                               \\--(retry)--> agent
                    \\--(input blocked)--> END

- Handoff SalesAgent <-> CompareAgent la mot truong trong state; tool handoff doi truong do.
- place_order khong chay ngay: node confirm_order goi interrupt() de nguoi dung bam
  Xac nhan / Huy, roi graph chay tiep tu cho dung (state luu trong PostgreSQL).
- check: guardrail output, kiem tra hanh dong da tuyen bo, kiem tra so lieu so sanh.
  Moi loai duoc yeu cau viet lai toi da mot lan.
"""

from __future__ import annotations

import json
import logging
import time
import uuid
from operator import add
from typing import Annotated, Any, Optional, TypedDict

from langgraph.config import get_stream_writer
from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt

from app import tracing
from app.agent import llm
from app.agent.prompts import HANDOFF_MAP, build_agent_configs, localize
from app.agent.tools import TOOL_DEFS, TOOL_DISPATCH
from app.config import GUARD_MODEL, MAX_ITERATIONS
from app.guardrails import check_input, check_input_llm, check_output, unbacked_action_claims
from app.services.compare import unsupported_numbers

logger = logging.getLogger("agent")

AGENT_CONFIGS = build_agent_configs(TOOL_DEFS)
AGENT_KEYS = {cfg.name: key for key, cfg in AGENT_CONFIGS.items()}

# Tool can session_id that cua cuoc hoi thoai (model khong biet, khong duoc bia)
SESSION_TOOLS = {"request_human_support", "save_customer_info", "place_order"}
# So luot hoi thoai truoc do gui kem cho model
HISTORY_TURNS = 10


# ------------------------------------------------------------------
# STATE
# ------------------------------------------------------------------
def _turn_reducer(current: Optional[list], update: Any) -> list:
    """Them message vao luot hien tai; {'replace': [...]} de bat dau luot moi."""
    if isinstance(update, dict) and "replace" in update:
        return list(update["replace"])
    return (current or []) + list(update)


def _transcript_reducer(current: Optional[list], update: list) -> list:
    return ((current or []) + list(update))[-HISTORY_TURNS * 2 :]


class State(TypedDict, total=False):
    transcript: Annotated[list[dict], _transcript_reducer]  # cac luot truoc: user + cau tra loi
    turn: Annotated[list[dict], _turn_reducer]  # luot hien tai: user, assistant, tool, ghi chu
    agent: str  # "sales" | "compare"
    lang: str  # "vi" | "en" - ngon ngu khach chon tren giao dien
    turn_id: str
    started_at: float
    retried: Annotated[list[str], add]
    order_decisions: dict  # tool_call_id -> {"approved": bool}
    answer: Optional[str]
    intent: Optional[str]
    warning: Optional[str]


LANGS = ("vi", "en")

BLOCKED_MESSAGE = {
    "vi": "Phát hiện nội dung không hợp lệ. Bạn vui lòng nhập câu hỏi bình thường nhé.",
    "en": "This message looks like an attempt to change my instructions. Please ask a normal question.",
}
OUTPUT_BLOCKED_MESSAGE = {
    "vi": "Xin lỗi, đã xảy ra lỗi khi xử lý câu trả lời. Bạn vui lòng hỏi lại nhé.",
    "en": "Sorry, something went wrong while preparing the answer. Please ask again.",
}
TOO_MANY_ROUNDS_MESSAGE = {
    "vi": "Xin lỗi, mình chưa xử lý được yêu cầu này. Bạn thử hỏi đơn giản hơn nhé.",
    "en": "Sorry, I couldn't finish this request. Please try a simpler question.",
}


def new_turn_input(message: str, lang: str = "vi") -> dict:
    """Input cho mot luot moi."""
    return {
        "lang": lang if lang in LANGS else "vi",
        "turn": {"replace": [{"role": "user", "content": message}]},
        "turn_id": uuid.uuid4().hex[:12],
        "started_at": time.time(),
        "retried": [],
        "order_decisions": {},
        "answer": None,
        "intent": None,
        "warning": None,
    }


# ------------------------------------------------------------------
# HELPERS
# ------------------------------------------------------------------
def _session_id(config) -> str:
    return config["configurable"]["thread_id"]


def _writer():
    try:
        return get_stream_writer()
    except Exception:  # khi chay invoke() khong stream
        return lambda _event: None


def tools_called(turn: list[dict]) -> list[str]:
    return [
        tc["function"]["name"]
        for m in turn
        if m.get("role") == "assistant"
        for tc in m.get("tool_calls") or []
    ]


def _tool_outputs(turn: list[dict]) -> list[str]:
    return [m["content"] for m in turn if m.get("role") == "tool"]


def _last_tool_calls(turn: list[dict]) -> list[dict]:
    for m in reversed(turn):
        if m.get("role") == "assistant":
            return m.get("tool_calls") or []
    return []


def _llm_messages(state: State) -> list[dict]:
    cfg = AGENT_CONFIGS[state.get("agent") or "sales"]
    system = localize(cfg.system_prompt, _lang(state))
    return [{"role": "system", "content": system}, *state.get("transcript", []), *state["turn"]]


def _lang(state: State) -> str:
    return state.get("lang") if state.get("lang") in LANGS else "vi"


# ------------------------------------------------------------------
# NODES
# ------------------------------------------------------------------
def start(state: State, config) -> dict:
    user_msg = state["turn"][0]["content"]
    result = check_input(user_msg)
    if result.passed:
        result = check_input_llm(user_msg, GUARD_MODEL)
    if result.passed:
        return {"agent": state.get("agent") or "sales"}
    logger.warning(f"[Guardrail] Input blocked: {result.reason}")
    return {"answer": BLOCKED_MESSAGE[_lang(state)], "intent": "blocked", "warning": result.reason}


def agent(state: State, config) -> dict:
    write = _writer()
    cfg = AGENT_CONFIGS[state.get("agent") or "sales"]
    rounds = sum(1 for m in state["turn"] if m.get("role") == "assistant")
    logger.info(f"[{cfg.name}] Vong {rounds + 1}")

    result = llm.chat(
        _llm_messages(state),
        tools=cfg.tools,
        on_token=lambda t: write({"type": "token", "text": t}),
    )
    tracing.record(
        "llm",
        cfg.name,
        session_id=_session_id(config),
        turn_id=state.get("turn_id"),
        latency_ms=result.latency_ms,
        prompt_tokens=result.prompt_tokens,
        completion_tokens=result.completion_tokens,
        detail={"model": result.model, "attempts": result.attempts, "tool_calls": [c["function"]["name"] for c in result.tool_calls]},
    )
    if result.tool_calls and (result.message.get("content") or ""):
        write({"type": "reset"})  # chu truoc khi goi tool chi la nhap
    return {"turn": [result.message]}


def route_after_agent(state: State) -> str:
    calls = _last_tool_calls(state["turn"])
    last = state["turn"][-1]
    if last.get("role") != "assistant" or not calls:
        return "check"
    rounds = sum(1 for m in state["turn"] if m.get("role") == "assistant")
    if rounds >= MAX_ITERATIONS:
        return "too_many_rounds"
    # Chi hoi xac nhan khi don da du thong tin; thieu ten/SDT thi tools node bao model hoi khach
    if any(c["function"]["name"] == "place_order" and _has_contact(c) for c in calls):
        return "confirm_order"
    return "tools"


def _has_contact(call: dict) -> bool:
    args = _parse_args(call)
    return bool(str(args.get("customer_name") or "").strip()) and bool(
        str(args.get("customer_phone") or "").strip()
    )


def confirm_order(state: State, config) -> dict:
    """Dung lai cho nguoi dung xac nhan don hang. Node nay chi doc, chay lai an toan."""
    from app.services.product import get_product_details

    orders = []
    for call in _last_tool_calls(state["turn"]):
        if call["function"]["name"] != "place_order" or not _has_contact(call):
            continue
        args = _parse_args(call)
        product = get_product_details(int(args.get("product_id", 0)))
        orders.append(
            {
                "tool_call_id": call["id"],
                "product_id": args.get("product_id"),
                "product_name": product.name if product else None,
                "unit_price": product.price if product else None,
                "stock": product.stock if product else None,
                "quantity": args.get("quantity"),
                "customer_name": args.get("customer_name"),
                "customer_phone": args.get("customer_phone"),
            }
        )

    decision = interrupt({"type": "confirm_order", "orders": orders})
    approved = bool(decision.get("approved")) if isinstance(decision, dict) else bool(decision)
    return {"order_decisions": {o["tool_call_id"]: {"approved": approved} for o in orders}}


def _parse_args(call: dict) -> dict:
    try:
        return json.loads(call["function"].get("arguments") or "{}")
    except json.JSONDecodeError:
        return {}


def tools(state: State, config) -> dict:
    write = _writer()
    session_id = _session_id(config)
    current = state.get("agent") or "sales"
    new_agent = current
    out: list[dict] = []

    for call in _last_tool_calls(state["turn"]):
        name = call["function"]["name"]
        args = _parse_args(call)
        write({"type": "tool", "name": name})
        logger.info(f"[{AGENT_CONFIGS[new_agent].name}] Tool: {name}({args})")
        started = time.time()
        ok = True

        if name in HANDOFF_MAP:
            new_agent = HANDOFF_MAP[name]
            result = f"Da chuyen sang {AGENT_CONFIGS[new_agent].name}."
            logger.info(f"[Handoff] -> {AGENT_CONFIGS[new_agent].name}")
        elif name == "place_order" and not _has_contact(call):
            result = json.dumps(
                {
                    "status": "need_customer_info",
                    "message": "Chua tao don. Hoi khach HO TEN va SO DIEN THOAI nguoi nhan, "
                    "roi goi lai place_order kem thong tin do.",
                },
                ensure_ascii=False,
            )
        elif name == "place_order" and not state.get("order_decisions", {}).get(call["id"], {}).get("approved"):
            decided = call["id"] in state.get("order_decisions", {})
            result = json.dumps(
                {
                    "status": "cancelled",
                    "message": (
                        "Khach da bam HUY tren the xac nhan nen don hang KHONG duoc tao."
                        if decided
                        else "Khach chua xac nhan nen don hang KHONG duoc tao."
                    ),
                },
                ensure_ascii=False,
            )
        else:
            if name in SESSION_TOOLS:
                args["session_id"] = session_id
            if name == "compare_products":
                args["lang"] = _lang(state)  # nhan bang so sanh theo ngon ngu khach
            fn = TOOL_DISPATCH.get(name)
            try:
                result = fn(args) if fn else json.dumps({"error": f"Tool '{name}' khong ton tai"})
            except Exception as exc:
                ok = False
                logger.error(f"[Tool Error] {name}: {exc}")
                result = json.dumps({"error": str(exc)}, ensure_ascii=False)

        tracing.record(
            "tool",
            name,
            session_id=session_id,
            turn_id=state.get("turn_id"),
            latency_ms=int((time.time() - started) * 1000),
            ok=ok,
            detail={"args": args},
        )
        out.append({"role": "tool", "tool_call_id": call["id"], "content": result})

    update: dict = {"turn": out}
    if new_agent != current:
        update["agent"] = new_agent
    return update


def check(state: State, config) -> dict:
    """Kiem tra cau tra loi; neu sai thi them ghi chu va cho agent viet lai (moi loai 1 lan)."""
    answer = state["turn"][-1].get("content") or ""
    called = tools_called(state["turn"])
    retried = state.get("retried", [])
    write = _writer()

    def _retry(kind: str, note: str) -> dict:
        logger.warning(f"[Check:{kind}] {note}")
        write({"type": "reset"})
        return {"turn": [{"role": "user", "content": f"[He thong] {note}"}], "retried": [kind]}

    warnings = []

    claims = unbacked_action_claims(answer, called)
    if claims:
        if "action" not in retried:
            return _retry(
                "action",
                "Cau tra loi noi da thuc hien hanh dong nhung luot nay chua goi tool: "
                f"{', '.join(claims)}. Neu can thuc hien, hay goi tool do roi tra loi lai. "
                "Neu viec do da lam o luot truoc, tra loi lai va noi ro la da tao tu truoc.",
            )
        warnings.append(f"Cau tra loi noi da {', '.join(claims)} nhung khong goi tool")

    if "compare_products" in called:
        # So khach tu noi (vd "Nokia 3310") khong phai so bia
        bad = unsupported_numbers(answer, [state["turn"][0]["content"], *_tool_outputs(state["turn"])])
        if bad:
            if "numbers" not in retried:
                return _retry(
                    "numbers",
                    f"Cau tra loi co so lieu khong co trong bang so sanh: {', '.join(bad)}. "
                    "Viet lai, chep nguyen bang table_markdown va chi dung so co trong bang.",
                )
            warnings.append(f"So lieu chua kiem chung: {', '.join(bad)}")

    output = check_output(answer)
    if not output.passed:
        logger.warning(f"[Guardrail] Output blocked: {output.reason} | {answer[:300]!r}")
        answer = OUTPUT_BLOCKED_MESSAGE[_lang(state)]

    return {
        "answer": answer,
        "intent": AGENT_CONFIGS[state.get("agent") or "sales"].name,
        "warning": "; ".join(warnings) or None,
    }


def route_after_check(state: State) -> str:
    return "agent" if state["turn"][-1].get("role") == "user" else "finish"


def too_many_rounds(state: State, config) -> dict:
    logger.warning(f"[Agent] Dat gioi han {MAX_ITERATIONS} vong")
    return {
        "answer": TOO_MANY_ROUNDS_MESSAGE[_lang(state)],
        "intent": "error",
        "warning": f"Dat gioi han {MAX_ITERATIONS} vong",
    }


def finish(state: State, config) -> dict:
    """Luu luot vao transcript (chi user + cau tra loi cuoi) va ghi trace tong."""
    wall_ms = int((time.time() - state.get("started_at", time.time())) * 1000)
    tracing.record(
        "turn",
        state.get("intent") or "unknown",
        session_id=_session_id(config),
        turn_id=state.get("turn_id"),
        # Thoi gian xu ly that (LLM + tool); thoi gian tinh ca luc cho khach o detail
        latency_ms=tracing.active_ms(state.get("turn_id")) if state.get("turn_id") else wall_ms,
        ok=not state.get("warning"),
        detail={
            "tools": tools_called(state["turn"]),
            "warning": state.get("warning"),
            "retried": state.get("retried", []),
            "wall_ms": wall_ms,
        },
    )
    return {
        "transcript": [
            {"role": "user", "content": state["turn"][0]["content"]},
            {"role": "assistant", "content": state.get("answer") or ""},
        ]
    }


def route_after_start(state: State) -> str:
    return "finish" if state.get("intent") == "blocked" else "agent"


# ------------------------------------------------------------------
# BUILD
# ------------------------------------------------------------------
def build_graph(checkpointer=None):
    g = StateGraph(State)
    g.add_node("start", start)
    g.add_node("agent", agent)
    g.add_node("confirm_order", confirm_order)
    g.add_node("tools", tools)
    g.add_node("check", check)
    g.add_node("too_many_rounds", too_many_rounds)
    g.add_node("finish", finish)

    g.add_edge(START, "start")
    g.add_conditional_edges("start", route_after_start, ["agent", "finish"])
    g.add_conditional_edges(
        "agent", route_after_agent, ["tools", "confirm_order", "check", "too_many_rounds"]
    )
    g.add_edge("confirm_order", "tools")
    g.add_edge("tools", "agent")
    g.add_conditional_edges("check", route_after_check, ["agent", "finish"])
    g.add_edge("too_many_rounds", "finish")
    g.add_edge("finish", END)
    return g.compile(checkpointer=checkpointer)
