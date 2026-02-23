"""
Pydantic schemas dung chung cho FastAPI request / response.
Tach khoi agent_core.py de frontend / client doc doc lap.
"""

from typing import Any, Optional
from pydantic import BaseModel, Field


# ------------------------------------------------------------------
# REQUEST
# ------------------------------------------------------------------
class ChatRequest(BaseModel):
    message: str = Field(
        ..., min_length=1, max_length=1000, description="Cau hoi cua nguoi dung"
    )
    session_id: Optional[str] = Field(None, description="ID phien hoi thoai (tuy chon)")


# ------------------------------------------------------------------
# RESPONSE
# ------------------------------------------------------------------
class ChatResponse(BaseModel):
    intent: str
    answer_markdown: str
    tools_called: list[str]
    warning: Optional[str] = None
    session_id: Optional[str] = None


class ProductSchema(BaseModel):
    id: int
    name: str
    brand: str
    price: float
    specs: dict[str, Any]
    description: str


class ProductListResponse(BaseModel):
    total: int
    products: list[ProductSchema]


class HealthResponse(BaseModel):
    status: str
    postgres: str
    qdrant: str
    ollama: str
