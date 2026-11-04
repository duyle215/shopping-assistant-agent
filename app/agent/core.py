"""
Shopping Agent - lop boc quanh agent graph (app/agent/graph.py).

  - Trang thai hoi thoai luu trong PostgreSQL (LangGraph PostgresSaver), thread_id = session_id,
    nen restart server khong mat hoi thoai.
  - run():     chay mot luot, tra ve AgentResponse (dung cho /api/chat va bo danh gia).
  - stream():  chay mot luot va phat su kien (token, tool, confirm, final) cho SSE.
  - confirm(): tra loi cau hoi xac nhan don hang (Xac nhan / Huy) roi chay tiep.
"""

from __future__ import annotations

import atexit
import logging
from typing import Iterator, Optional

from langgraph.types import Command

from app.agent.graph import build_graph, new_turn_input, tools_called
from app.agent.llm import QuotaExhausted
from app.agent.schemas import AgentResponse

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
logger = logging.getLogger("agent")

BUSY_MESSAGE = "Hệ thống đang quá tải, bạn vui lòng thử lại sau ít phút nhé."


def _postgres_checkpointer():
    from langgraph.checkpoint.postgres import PostgresSaver
    from psycopg.rows import dict_row
    from psycopg_pool import ConnectionPool

    from app.config import PG_DSN

    pool = ConnectionPool(
        PG_DSN,
        min_size=1,
        max_size=10,
        kwargs={"autocommit": True, "prepare_threshold": 0, "row_factory": dict_row},
        open=True,
    )
    atexit.register(pool.close)
    saver = PostgresSaver(pool)
    saver.setup()
    return saver


class ShoppingAgent:
    def __init__(self, checkpointer=None) -> None:
        self.checkpointer = checkpointer if checkpointer is not None else _postgres_checkpointer()
        self.graph = build_graph(self.checkpointer)

    # ------------------------------------------------------------------
    @staticmethod
    def new_session_id() -> str:
        import uuid

        return str(uuid.uuid4())

    def _config(self, session_id: str) -> dict:
        return {"configurable": {"thread_id": session_id}}

    def pending_confirmation(self, session_id: str) -> Optional[dict]:
        """Cau hoi xac nhan dang cho (neu co)."""
        snapshot = self.graph.get_state(self._config(session_id))
        for task in snapshot.tasks:
            for intr in task.interrupts:
                return intr.value
        return None

    def _response(self, session_id: str) -> AgentResponse:
        snapshot = self.graph.get_state(self._config(session_id))
        values = snapshot.values
        pending = self.pending_confirmation(session_id)
        if pending:
            return AgentResponse(
                intent="confirm_order",
                answer_markdown="Vui lòng xác nhận đơn hàng trước khi mình đặt.",
                tools_called=tools_called(values.get("turn", [])),
                session_id=session_id,
                pending_confirmation=pending,
            )
        return AgentResponse(
            intent=values.get("intent") or "unknown",
            answer_markdown=values.get("answer") or "",
            tools_called=tools_called(values.get("turn", [])),
            warning=values.get("warning"),
            session_id=session_id,
        )

    def _cancel_pending(self, session_id: str) -> None:
        """Khach gui tin moi thay vi bam nut: coi nhu huy don dang cho xac nhan."""
        if self.pending_confirmation(session_id):
            logger.info(f"[Confirm] {session_id}: tin nhan moi -> huy don dang cho")
            self.graph.invoke(Command(resume={"approved": False}), self._config(session_id))

    # ------------------------------------------------------------------
    def _busy(self, session_id: str, exc: Exception) -> AgentResponse:
        logger.error(f"[Agent] LLM khong dung duoc: {exc}")
        return AgentResponse(
            intent="error",
            answer_markdown=BUSY_MESSAGE,
            tools_called=[],
            warning=str(exc),
            session_id=session_id,
        )

    def run(self, user_message: str, session_id: Optional[str] = None) -> AgentResponse:
        session_id = session_id or self.new_session_id()
        try:
            self._cancel_pending(session_id)
            self.graph.invoke(new_turn_input(user_message), self._config(session_id))
        except QuotaExhausted as exc:
            return self._busy(session_id, exc)
        return self._response(session_id)

    def confirm(self, session_id: str, approved: bool) -> AgentResponse:
        if not self.pending_confirmation(session_id):
            return self._response(session_id)
        try:
            self.graph.invoke(Command(resume={"approved": approved}), self._config(session_id))
        except QuotaExhausted as exc:
            return self._busy(session_id, exc)
        return self._response(session_id)

    # ------------------------------------------------------------------
    def _stream(self, graph_input, session_id: str) -> Iterator[dict]:
        try:
            for chunk in self.graph.stream(
                graph_input, self._config(session_id), stream_mode="custom"
            ):
                yield chunk
        except QuotaExhausted as exc:
            yield {"type": "reset"}
            yield {"type": "final", **self._busy(session_id, exc).model_dump()}
            return
        yield {"type": "final", **self._response(session_id).model_dump()}

    def stream(self, user_message: str, session_id: Optional[str] = None) -> Iterator[dict]:
        session_id = session_id or self.new_session_id()
        try:
            self._cancel_pending(session_id)
        except QuotaExhausted as exc:
            yield {"type": "final", **self._busy(session_id, exc).model_dump()}
            return
        yield from self._stream(new_turn_input(user_message), session_id)

    def stream_confirm(self, session_id: str, approved: bool) -> Iterator[dict]:
        if not self.pending_confirmation(session_id):
            yield {"type": "final", **self._response(session_id).model_dump()}
            return
        yield from self._stream(Command(resume={"approved": approved}), session_id)

    def clear(self, session_id: str) -> None:
        self.checkpointer.delete_thread(session_id)
