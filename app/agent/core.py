"""
Shopping Agent Core - Agent Loop.

Day la trung tam dieu phoi:
  - Agent Loop:   LLM tu quyet dinh goi tool, lap lai cho den khi xong.
  - Handoffs:     SalesAgent <-> CompareAgent uy quyen cho nhau.
  - Sessions:     Nho lich su hoi thoai (hieu "cai do" la gi).
  - Guardrails:   Kiem tra input/output, chan prompt injection.
"""

from __future__ import annotations

import json
import logging
from concurrent.futures import ThreadPoolExecutor

from openai import OpenAI

from app.config import AGENT_API_KEY, AGENT_BASE_URL, LLM_MODEL, MAX_ITERATIONS
from app.guardrails import check_input, check_output, unbacked_action_claims
from app.sessions import SessionStore
from app.agent.schemas import AgentResponse
from app.agent.prompts import HANDOFF_MAP, build_agent_configs
from app.agent.tools import TOOL_DEFS, TOOL_DISPATCH
from app.services.compare import unsupported_numbers

# ------------------------------------------------------------------
# LOGGING
# ------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
logger = logging.getLogger("agent")

# ------------------------------------------------------------------
# BUILD AGENT CONFIGS (lien ket prompts + tool defs)
# ------------------------------------------------------------------
AGENT_CONFIGS = build_agent_configs(TOOL_DEFS)

# Tool can session_id that cua cuoc hoi thoai
SESSION_TOOLS = {"request_human_support", "save_customer_info"}


# ------------------------------------------------------------------
# SHOPPING AGENT CLASS
# ------------------------------------------------------------------
class ShoppingAgent:
    """
    Agent tu van mua dien thoai voi day du:
    - Agent Loop (LLM tu goi tool, lap lai den khi xong)
    - Handoffs (SalesAgent <-> CompareAgent)
    - Sessions (nho lich su hoi thoai)
    - Guardrails (kiem tra input/output)
    """

    def __init__(self) -> None:
        self.client = OpenAI(
            base_url=AGENT_BASE_URL,
            api_key=AGENT_API_KEY,
        )
        self.sessions = SessionStore(max_turns=20, ttl_seconds=3600)
        self._executor = ThreadPoolExecutor(max_workers=2)

    def run(self, user_message: str, session_id: str | None = None) -> AgentResponse:
        """Entry point chinh. Chay agent loop voi guardrails va sessions."""

        if not session_id:
            session_id = self.sessions.new_id()

        # -- Guardrail: Kiem tra input --
        input_check = check_input(user_message)
        if not input_check.passed:
            logger.warning(f"[Guardrail] Input blocked: {input_check.reason}")
            return AgentResponse(
                intent="blocked",
                answer_markdown=input_check.reason or "Tin nhan khong hop le.",
                tools_called=[],
                warning=input_check.reason,
                session_id=session_id,
            )

        # -- Load lich su hoi thoai --
        history = self.sessions.get_messages(session_id)

        # -- Xay dung messages: system + history + user --
        current_agent = AGENT_CONFIGS["sales"]
        messages: list[dict] = [
            {"role": "system", "content": current_agent.system_prompt}
        ]
        messages.extend(history)
        messages.append({"role": "user", "content": user_message})

        tools_called: list[str] = []
        tool_outputs: list[str] = []  # du lieu tool tra ve, de doi chieu so lieu
        number_check_retried = False
        action_check_retried = False
        warning: str | None = None

        # ====== AGENT LOOP ======
        for iteration in range(MAX_ITERATIONS):
            logger.info(
                f"[{current_agent.name}] Vong {iteration + 1} | "
                f"So messages: {len(messages)}"
            )

            response = self.client.chat.completions.create(
                model=LLM_MODEL,
                messages=messages,
                tools=current_agent.tools,
            )

            msg = response.choices[0].message

            # ---- LLM tra ve van ban (ket thuc loop) ----
            if not msg.tool_calls:
                answer = msg.content or ""

                # Noi "da dat hang" / "nhan vien se lien he" thi phai that su goi tool
                claims = unbacked_action_claims(answer, tools_called)
                if claims and not action_check_retried:
                    action_check_retried = True
                    logger.warning(f"[ActionCheck] Noi da lam nhung chua goi: {claims}")
                    messages.append({"role": "assistant", "content": answer})
                    messages.append(
                        {
                            "role": "user",
                            "content": (
                                "[He thong] Cau tra loi noi da thuc hien hanh dong nhung luot nay "
                                f"chua goi tool: {', '.join(claims)}. Neu can thuc hien, hay goi "
                                "tool do roi tra loi lai. Neu viec do da lam o luot truoc, tra loi "
                                "lai va noi ro la da tao tu truoc."
                            ),
                        }
                    )
                    continue
                if claims:
                    warning = f"Cau tra loi noi da {', '.join(claims)} nhung khong goi tool"
                    logger.warning(f"[ActionCheck] {warning}")

                # Cau tra loi so sanh: moi con so phai co trong du lieu tool tra ve
                if "compare_products" in tools_called:
                    bad = unsupported_numbers(answer, tool_outputs)
                    if bad and not number_check_retried:
                        number_check_retried = True
                        logger.warning(f"[NumberCheck] So khong co trong bang: {bad}, yeu cau viet lai")
                        messages.append({"role": "assistant", "content": answer})
                        messages.append(
                            {
                                "role": "user",
                                "content": (
                                    "[He thong] Cau tra loi co so lieu khong co trong bang so sanh: "
                                    f"{', '.join(bad)}. Viet lai, chep nguyen bang table_markdown "
                                    "va chi dung so co trong bang."
                                ),
                            }
                        )
                        continue
                    if bad:
                        warning = f"So lieu chua kiem chung: {', '.join(bad)}"
                        logger.warning(f"[NumberCheck] {warning}")
                logger.info(
                    f"[{current_agent.name}] Hoan thanh sau {iteration + 1} vong"
                )

                # Guardrail: Kiem tra output
                output_check = check_output(answer)
                if not output_check.passed:
                    logger.warning(f"[Guardrail] Output blocked: {output_check.reason}")
                    answer = (
                        "Xin loi, da xay ra loi khi xu ly cau tra loi. "
                        "Vui long hoi lai."
                    )

                # Luu vao session
                self.sessions.add_message(session_id, "user", user_message)
                self.sessions.add_message(session_id, "assistant", answer)

                return AgentResponse(
                    intent=current_agent.name,
                    answer_markdown=answer,
                    tools_called=tools_called,
                    warning=warning,
                    session_id=session_id,
                )

            # ---- LLM goi tool(s) ----
            messages.append(msg)

            for tc in msg.tool_calls:
                fn_name = tc.function.name
                fn_args_raw = tc.function.arguments or "{}"
                try:
                    fn_args = json.loads(fn_args_raw)
                except json.JSONDecodeError:
                    fn_args = {}

                logger.info(f"[{current_agent.name}] Tool: {fn_name}({fn_args})")

                # -- Handoff --
                if fn_name in HANDOFF_MAP:
                    target_key = HANDOFF_MAP[fn_name]
                    current_agent = AGENT_CONFIGS[target_key]
                    messages[0] = {
                        "role": "system",
                        "content": current_agent.system_prompt,
                    }
                    messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": tc.id,
                            "content": f"Da chuyen sang {current_agent.name}.",
                        }
                    )
                    tools_called.append(fn_name)
                    logger.info(f"[Handoff] -> {current_agent.name}")
                    continue

                # -- Thuc thi tool --
                # session_id do server gan, model khong biet (va khong duoc bia) gia tri nay
                if fn_name in SESSION_TOOLS:
                    fn_args["session_id"] = session_id
                tools_called.append(fn_name)
                dispatch_fn = TOOL_DISPATCH.get(fn_name)
                if dispatch_fn:
                    try:
                        result_str = dispatch_fn(fn_args)
                    except Exception as e:
                        logger.error(f"[Tool Error] {fn_name}: {e}")
                        result_str = json.dumps({"error": str(e)}, ensure_ascii=False)
                else:
                    result_str = json.dumps(
                        {"error": f"Tool '{fn_name}' khong ton tai"},
                        ensure_ascii=False,
                    )

                tool_outputs.append(result_str)
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "content": result_str,
                    }
                )

        # -- Vuot qua MAX_ITERATIONS --
        logger.warning(f"[Agent] Dat gioi han {MAX_ITERATIONS} vong lap!")
        return AgentResponse(
            intent="error",
            answer_markdown=(
                "Xin loi, toi khong the xu ly yeu cau nay luc nay. "
                "Vui long thu lai voi cau hoi don gian hon."
            ),
            tools_called=tools_called,
            warning=f"Dat gioi han {MAX_ITERATIONS} vong lap",
            session_id=session_id,
        )
