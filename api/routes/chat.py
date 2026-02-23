"""
POST /chat  - gui cau hoi, nhan tra loi Markdown tu Shopping Agent
"""

import uuid

from fastapi import APIRouter, HTTPException

from api.dependencies import get_agent
from api.schemas import ChatRequest, ChatResponse

router = APIRouter(prefix="/chat", tags=["Chat"])


@router.post("", response_model=ChatResponse)
def chat(req: ChatRequest) -> ChatResponse:
    """
    Nhan cau hoi nguoi dung, chay qua luong Agent 3 buoc,
    tra ve cau tra loi dang Markdown.
    """
    try:
        agent = get_agent()
        result = agent.run(req.message)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    session_id = req.session_id or str(uuid.uuid4())

    return ChatResponse(
        intent=result.intent,
        answer_markdown=result.answer_markdown,
        tools_called=result.tools_called,
        warning=result.warning,
        session_id=session_id,
    )
