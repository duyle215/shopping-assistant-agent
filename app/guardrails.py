"""
Guardrails - Kiem tra dau vao / dau ra.

Chay truoc va sau agent execution, fail fast khi phat hien van de.
- Input:  chong prompt injection, kiem tra do dai, noi dung cam.
- Output: chan ro ri thong tin noi bo he thong.
"""

from __future__ import annotations

import re

from pydantic import BaseModel


class GuardrailResult(BaseModel):
    """Ket qua kiem tra guardrail."""

    passed: bool
    reason: str | None = None


# ------------------------------------------------------------------
# INPUT GUARDRAILS
# ------------------------------------------------------------------

# Regex phat hien prompt injection (case-insensitive)
INJECTION_PATTERNS: list[str] = [
    r"ignore\s+(all\s+)?previous\s+instructions",
    r"ignore\s+(all\s+)?above",
    r"disregard\s+(all\s+)?previous",
    r"forget\s+(all\s+)?previous",
    r"you\s+are\s+now\s+a",
    r"act\s+as\s+if\s+you\s+are",
    r"pretend\s+you\s+are",
    r"system\s*:\s*",
    r"<\|im_start\|>",
    r"<\|im_end\|>",
    r"\[INST\]",
    r"\[/INST\]",
    r"###\s*(system|instruction|human)",
    r"<\s*script\s*>",
    r"<\s*iframe\s*>",
]

MAX_MESSAGE_LENGTH = 2000


def check_input(message: str) -> GuardrailResult:
    """Kiem tra tin nhan dau vao truoc khi gui cho agent."""

    # 1. Tin nhan trong
    if not message or not message.strip():
        return GuardrailResult(passed=False, reason="Tin nhan trong.")

    # 2. Qua dai
    if len(message) > MAX_MESSAGE_LENGTH:
        return GuardrailResult(
            passed=False,
            reason=f"Tin nhan qua dai (toi da {MAX_MESSAGE_LENGTH} ky tu).",
        )

    # 3. Prompt injection
    lower = message.lower()
    for pattern in INJECTION_PATTERNS:
        if re.search(pattern, lower):
            return GuardrailResult(
                passed=False,
                reason="Phat hien noi dung khong hop le. Vui long nhap cau hoi binh thuong.",
            )

    return GuardrailResult(passed=True)


# ------------------------------------------------------------------
# OUTPUT GUARDRAILS
# ------------------------------------------------------------------

# Regex phat hien ro ri thong tin noi bo
LEAKED_PATTERNS: list[str] = [
    r"score:\s*\d+\.\d{3,}",
    r"query_vector",
    r"embedding\s*=",
    r"system\s*prompt",
    r"TOOL_DEFINITIONS",
    r"qdrant_data",
    r"vector[\s_]*store",
    r"cosine[\s_]*(similarity|distance)",
    r"PG_URL",
    r"OPENAI_API_KEY",
    r"sk-proj-",
]


def check_output(response: str) -> GuardrailResult:
    """Kiem tra cau tra loi truoc khi gui cho nguoi dung."""

    if not response or not response.strip():
        return GuardrailResult(
            passed=False,
            reason="Cau tra loi trong.",
        )

    lower = response.lower()
    for pattern in LEAKED_PATTERNS:
        if re.search(pattern, lower):
            return GuardrailResult(
                passed=False,
                reason="Cau tra loi co the chua thong tin noi bo he thong.",
            )

    return GuardrailResult(passed=True)
