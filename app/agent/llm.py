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

from app.config import AGENT_API_KEY, AGENT_BASE_URL, LLM_FALLBACK_MODEL, LLM_MODEL

logger = logging.getLogger("llm")

_client: Optional[OpenAI] = None
MAX_RETRY_WAIT = 90.0
# model -> thoi diem het "phat" quota; trong luc do goi thang model du phong
_exhausted_until: dict[str, float] = {}


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


class QuotaExhausted(Exception):
    """Provider bao phai cho qua lau (vd het quota ngay): khong ngoi cho, chuyen model hoac bao loi."""

    def __init__(self, model: str, wait_seconds: Optional[float]):
        self.model = model
        self.wait_seconds = wait_seconds
        mins = f"{wait_seconds / 60:.0f} phut" if wait_seconds else "?"
        super().__init__(f"Model {model} het han muc, phai cho khoang {mins}")


def _parse_duration(text: str) -> Optional[float]:
    """'40m50.9s' -> 2450.9 ; '1h2m3s' -> 3723 ; '37s' -> 37."""
    import re

    m = re.fullmatch(r"(?:(\d+)h)?(?:(\d+)m)?(?:([\d.]+)s)?", text.strip())
    if not m or not any(m.groups()):
        return None
    h, mi, sec = m.groups()
    return int(h or 0) * 3600 + int(mi or 0) * 60 + float(sec or 0)


def _retry_after(exc: Exception) -> Optional[float]:
    """Thoi gian cho tu loi 429: header Retry-After, 'Please retry in 40m50s' hoac retryDelay."""
    import re

    response = getattr(exc, "response", None)
    header = response.headers.get("retry-after") if response is not None else None
    if header:
        try:
            return float(header)
        except ValueError:
            pass
    text = str(getattr(exc, "body", "")) + " " + str(exc)
    for pattern in (r"retry in ((?:\d+h)?(?:\d+m)?[\d.]+s)", r"retryDelay['\"]?\s*:\s*['\"]([\dhms.]+)['\"]"):
        m = re.search(pattern, text, re.IGNORECASE)
        if m:
            value = _parse_duration(m.group(1))
            if value is not None:
                return value
    return None


def chat(
    messages: list[dict],
    tools: Optional[list[dict]] = None,
    on_token: Optional[Callable[[str], None]] = None,
    model: str = LLM_MODEL,
    retries: int = 5,
) -> LLMResult:
    """Goi model chinh; neu het quota (phai cho lau) thi chuyen sang LLM_FALLBACK_MODEL."""
    models = [model]
    if LLM_FALLBACK_MODEL and LLM_FALLBACK_MODEL != model:
        models.append(LLM_FALLBACK_MODEL)
    now = time.time()
    available = [m for m in models if _exhausted_until.get(m, 0) <= now] or models[-1:]
    last: Optional[QuotaExhausted] = None
    for i, current in enumerate(available):
        try:
            # Doi model so voi model chinh -> chu ky thought_signature cu khong con hop le
            msgs = messages if current == model else _for_other_model(messages)
            return _chat_one(msgs, tools, on_token, current, retries)
        except QuotaExhausted as exc:
            last = exc
            _exhausted_until[current] = time.time() + min(exc.wait_seconds or 300, 3600)
            if i + 1 < len(available):
                logger.warning(f"[LLM] {exc}. Chuyen sang {available[i + 1]}")
    raise last  # type: ignore[misc]


def _for_other_model(messages: list[dict]) -> list[dict]:
    """thought_signature chi hop le voi model da tao ra no. Khi doi model giua luot,
    thay bang chu ky gia ma Gemini chap nhan cho lich su chuyen tu noi khac."""
    out = []
    for m in messages:
        if m.get("tool_calls"):
            calls = []
            for c in m["tool_calls"]:
                c = dict(c)
                if "extra_content" in c:
                    c["extra_content"] = {"google": {"thought_signature": "skip_thought_signature_validator"}}
                calls.append(c)
            m = {**m, "tool_calls": calls}
        out.append(m)
    return out


def _chat_one(
    messages: list[dict],
    tools: Optional[list[dict]],
    on_token: Optional[Callable[[str], None]],
    model: str,
    retries: int,
) -> LLMResult:
    """Mot model, stream. Thu lai khi bi gioi han toc do / loi tam thoi, chi khi chua stream chu nao."""
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
            if not transient or emitted:
                raise
            wait = delay
            if isinstance(exc, RateLimitError):
                hint = _retry_after(exc)
                logger.warning(f"[LLM] 429 {model}: {str(exc)[:200]}")
                if hint is not None and hint > MAX_RETRY_WAIT:
                    # Het quota ngay/gio: cho cung vo ich
                    raise QuotaExhausted(model, hint) from exc
                wait = max(hint or 0, 15.0 * attempt)
            if attempt == retries:
                if isinstance(exc, RateLimitError):
                    raise QuotaExhausted(model, None) from exc
                raise
            logger.warning(f"[LLM] {type(exc).__name__}, thu lai sau {wait:.0f}s")
            time.sleep(wait)
            delay *= 2
    raise RuntimeError("unreachable")
