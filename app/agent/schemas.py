"""
Pydantic schemas cho Agent.

Dinh nghia cau truc du lieu dung chung giua cac module:
  - ProductMetadata:  thong tin san pham tu Postgres
  - SearchResult:     ket qua tim kiem tu Qdrant
  - AgentResponse:    response cuoi cung tra ve frontend
"""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel


class ProductMetadata(BaseModel):
    """Thong tin san pham tra ve tu Postgres (moi thong so mot field co kieu)."""

    id: int
    name: str
    brand: str
    model: str
    price: int
    stock: int = 0
    chipset: str
    ram_gb: int
    storage_gb: list[int]
    screen_inch: float
    refresh_rate_hz: int
    battery_mah: int
    charging_w: Optional[int] = None
    main_camera_mp: int
    weight_g: Optional[int] = None
    os: str
    release_year: Optional[int] = None


class SearchResult(BaseModel):
    """Mot ket qua tim kiem tu Qdrant."""

    product_id: int
    name: str
    brand: str
    price: int
    ram_gb: int
    battery_mah: int
    max_storage_gb: int
    main_camera_mp: int
    score: float


class AgentResponse(BaseModel):
    """Response cuoi cung tra ve cho frontend."""

    intent: str
    answer_markdown: str
    tools_called: list[str]
    warning: Optional[str] = None
    session_id: str = ""
