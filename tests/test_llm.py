"""LLM client: doc thoi gian cho tu loi 429, chuyen model du phong khi het quota."""

from __future__ import annotations

import pytest

from app.agent import llm


def test_parse_wait_from_gemini_message():
    class E(Exception):
        body = None
        response = None

    assert llm._retry_after(E("limit exceeded. Please retry in 40m50.95s.")) == pytest.approx(2450.95)
    assert llm._retry_after(E("'retryDelay': '53s'")) == 53
    assert llm._retry_after(E("no hint here")) is None


def test_fallback_model_used_when_primary_quota_is_exhausted(monkeypatch):
    seen = []

    def fake_one(messages, tools, on_token, model, retries):
        seen.append((model, messages))
        if model == "primary":
            raise llm.QuotaExhausted("primary", 2400)
        return llm.LLMResult(message={"role": "assistant", "content": "ok"}, latency_ms=1, model=model)

    monkeypatch.setattr(llm, "_chat_one", fake_one)
    monkeypatch.setattr(llm, "LLM_FALLBACK_MODEL", "backup")
    monkeypatch.setattr(llm, "_exhausted_until", {})
    history = [
        {"role": "assistant", "content": None, "tool_calls": [
            {"id": "1", "type": "function", "function": {"name": "f", "arguments": "{}"},
             "extra_content": {"google": {"thought_signature": "real"}}}]},
    ]

    result = llm.chat(history, model="primary")

    assert result.model == "backup"
    sent = seen[1][1][0]["tool_calls"][0]["extra_content"]["google"]["thought_signature"]
    assert sent == "skip_thought_signature_validator"

    # lan sau bo qua model chinh trong luc no dang het quota
    seen.clear()
    llm.chat(history, model="primary")
    assert [m for m, _ in seen] == ["backup"]
