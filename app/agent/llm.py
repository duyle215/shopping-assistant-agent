"""
LLM client - goi Chat Completions (OpenAI-compatible) co stream va thu lai.

Tra ve message assistant dang dict, giu nguyen moi truong ma provider gui kem
(vd Gemini 3 gui `extra_content.google.thought_signature` trong tool call va BAT BUOC
phai gui lai o luot sau, neu khong se loi 400). Vi vay khong dung lop boc cua framework.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Callable, Optional

from openai import APIConnectionError, APIStatusError, OpenAI, RateLimitError

from app.config import AGENT_API_KEY, AGENT_BASE_URL, LLM_MODEL

logger = logging.getLogger("llm")

_client: Optional[OpenAI] = None


def client() -> OpenAI:
    global _client
    if _client is None:
        _client = OpenAI(base_url=AGENT_BASE_URL, api_key=AGENT_API_KEY, max_retries=0)
    return _client


@dataclass
class LLMResult:
    message: dict
    latency_ms: int
    prompt_tokens: Optional[int] = None
    completion_tokens: Optional[int] = None
    model: str = LLM_MODEL
    attempts: int = 1
    tool_calls: list[dict] = field(default_factory=list)


def _assemble(stream, on_token: Optional[Callable[[str], None]]) -> tuple[dict, Optional[object]]:
    """Ghep cac chunk stream thanh mot message assistant (ca tool calls)."""
    content = ""
    calls: list[dict] = []
    usage = None
    for chunk in stream:
        if getattr(chunk, "usage", None):
            usage = chunk.usage
        if not chunk.choices:
            continue
        delta = chunk.choices[0].delta
        if delta.content:
            content += delta.content
            if on_token:
                on_token(delta.content)
        for tc in delta.tool_calls or []:
            data = tc.model_dump(exclude_none=True)
            # OpenAI gui tung manh theo index; Gemini gui ca tool call mot lan, index rong
            if tc.id or not calls or (tc.index is not None and tc.index >= len(calls)):
                calls.append({"id": tc.id, "type": "function", "function": {"name": "", "arguments": ""}})
            cur = calls[-1] if tc.index is None else calls[min(tc.index, len(calls) - 1)]
            if tc.id:
                cur["id"] = tc.id
            fn = data.get("function", {})
            cur["function"]["name"] += fn.get("name", "")
            cur["function"]["arguments"] += fn.get("arguments", "")
            for key, value in data.items():
                if key not in ("index", "id", "type", "function"):
                    cur[key] = value  # vd extra_content (thought_signature)

    message: dict = {"role": "assistant", "content": content or None}
    if calls:
        message["tool_calls"] = calls
    return message, usage


def chat(
    messages: list[dict],
    tools: Optional[list[dict]] = None,
    on_token: Optional[Callable[[str], None]] = None,
    model: str = LLM_MODEL,
    retries: int = 4,
) -> LLMResult:
    """Goi model (stream). Thu lai khi bi gioi han toc do / loi tam thoi, chi khi chua stream chu nao."""
    delay = 2.0
    for attempt in range(1, retries + 1):
        started = time.time()
        emitted = False

        def _token(text: str) -> None:
            nonlocal emitted
            emitted = True
            if on_token:
                on_token(text)

        try:
            kwargs = dict(model=model, messages=messages, stream=True)
            if tools:
                kwargs["tools"] = tools
            try:
                stream = client().chat.completions.create(
                    **kwargs, stream_options={"include_usage": True}
                )
            except APIStatusError as exc:
                if exc.status_code != 400 or "stream_options" not in str(exc):
                    raise
                stream = client().chat.completions.create(**kwargs)
            message, usage = _assemble(stream, _token)
            return LLMResult(
                message=message,
                latency_ms=int((time.time() - started) * 1000),
                prompt_tokens=getattr(usage, "prompt_tokens", None),
                completion_tokens=getattr(usage, "completion_tokens", None),
                model=model,
                attempts=attempt,
                tool_calls=message.get("tool_calls", []),
            )
        except (RateLimitError, APIConnectionError, APIStatusError) as exc:
            transient = not isinstance(exc, APIStatusError) or exc.status_code >= 500 or isinstance(
                exc, RateLimitError
            )
            if not transient or emitted or attempt == retries:
                raise
            logger.warning(f"[LLM] {type(exc).__name__}, thu lai sau {delay:.0f}s")
            time.sleep(delay)
            delay *= 2
    raise RuntimeError("unreachable")
