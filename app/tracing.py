"""
Tracing - ghi lai tung buoc cua moi luot chat vao bang traces.

Moi lan goi LLM: agent, model, do tre, token. Moi lan goi tool: ten, do tre, thanh cong hay loi.
Cuoi luot: tong do tre, so vong, canh bao. Xem qua /api/traces va tab He thong.
Ghi trace khong bao gio duoc lam hong cau tra loi, nen moi loi deu bi bo qua.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from sqlalchemy import text

from app.db import get_engine

logger = logging.getLogger("tracing")


def record(
    kind: str,
    name: str,
    session_id: Optional[str] = None,
    turn_id: Optional[str] = None,
    latency_ms: Optional[int] = None,
    prompt_tokens: Optional[int] = None,
    completion_tokens: Optional[int] = None,
    ok: bool = True,
    detail: Optional[dict[str, Any]] = None,
) -> None:
    import json

    try:
        with get_engine().begin() as conn:
            conn.execute(
                text(
                    "INSERT INTO traces (session_id, turn_id, kind, name, latency_ms, "
                    "prompt_tokens, completion_tokens, ok, detail) VALUES "
                    "(:sid, :tid, :kind, :name, :lat, :pt, :ct, :ok, CAST(:detail AS JSONB))"
                ),
                {
                    "sid": session_id,
                    "tid": turn_id,
                    "kind": kind,
                    "name": name,
                    "lat": latency_ms,
                    "pt": prompt_tokens,
                    "ct": completion_tokens,
                    "ok": 1 if ok else 0,
                    "detail": json.dumps(detail or {}, ensure_ascii=False),
                },
            )
    except Exception as exc:  # pragma: no cover - tracing is best effort
        logger.debug(f"trace skipped: {exc}")


def summary(hours: int = 24) -> dict:
    """Thong ke nhanh cho tab He thong."""
    with get_engine().connect() as conn:
        turns = conn.execute(
            text(
                "SELECT count(*) AS n, avg(latency_ms) AS avg_ms, "
                "percentile_cont(0.95) WITHIN GROUP (ORDER BY latency_ms) AS p95_ms "
                "FROM traces WHERE kind = 'turn' AND created_at > now() - make_interval(hours => :h)"
            ),
            {"h": hours},
        ).one()
        llm = conn.execute(
            text(
                "SELECT count(*) AS calls, coalesce(sum(prompt_tokens), 0) AS prompt_tokens, "
                "coalesce(sum(completion_tokens), 0) AS completion_tokens, avg(latency_ms) AS avg_ms "
                "FROM traces WHERE kind = 'llm' AND created_at > now() - make_interval(hours => :h)"
            ),
            {"h": hours},
        ).one()
        tools = conn.execute(
            text(
                "SELECT name, count(*) AS calls, avg(latency_ms) AS avg_ms, sum(1 - ok) AS errors "
                "FROM traces WHERE kind = 'tool' AND created_at > now() - make_interval(hours => :h) "
                "GROUP BY name ORDER BY calls DESC"
            ),
            {"h": hours},
        ).fetchall()

    def _r(v):
        return None if v is None else round(float(v))

    return {
        "hours": hours,
        "turns": {"count": turns.n, "avg_ms": _r(turns.avg_ms), "p95_ms": _r(turns.p95_ms)},
        "llm": {
            "calls": llm.calls,
            "prompt_tokens": int(llm.prompt_tokens),
            "completion_tokens": int(llm.completion_tokens),
            "avg_ms": _r(llm.avg_ms),
        },
        "tools": [
            {"name": t.name, "calls": t.calls, "avg_ms": _r(t.avg_ms), "errors": int(t.errors)}
            for t in tools
        ],
    }


def recent(limit: int = 50, session_id: Optional[str] = None) -> list[dict]:
    query = (
        "SELECT id, session_id, turn_id, kind, name, latency_ms, prompt_tokens, "
        "completion_tokens, ok, detail, created_at FROM traces "
    )
    params: dict[str, Any] = {"limit": limit}
    if session_id:
        query += "WHERE session_id = :sid "
        params["sid"] = session_id
    query += "ORDER BY id DESC LIMIT :limit"
    with get_engine().connect() as conn:
        rows = conn.execute(text(query), params).fetchall()
    return [{**dict(r._mapping), "created_at": r.created_at.isoformat()} for r in rows]


def active_ms(turn_id: str) -> Optional[int]:
    """Thoi gian he thong that su xu ly mot luot (LLM + tool), khong tinh luc cho khach bam xac nhan."""
    try:
        with get_engine().connect() as conn:
            value = conn.execute(
                text("SELECT sum(latency_ms) FROM traces WHERE turn_id = :t AND kind IN ('llm', 'tool')"),
                {"t": turn_id},
            ).scalar()
        return int(value) if value is not None else None
    except Exception:  # pragma: no cover
        return None
