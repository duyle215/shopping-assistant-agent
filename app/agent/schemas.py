"""
Pydantic schemas cho Agent.

Dinh nghia cau truc du lieu dung chung giua cac module:
  - ProductMetadata:  thong tin san pham tu Postgres
  - SearchResult:     ket qua tim kiem tu Qdrant
  - AgentResponse:    response cuoi cung tra ve frontend
"""

from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel


class ProductMetadata(BaseModel):
    """Thong tin san pham tra ve tu Postgres."""

    id: int
    name: str
    brand: str
    price: float
    stock: int = 0
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
    session_id: str = ""
