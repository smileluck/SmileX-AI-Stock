from fastapi import APIRouter
from pydantic import BaseModel

from app.services.llm import chat

router = APIRouter(prefix="/ai", tags=["ai"])


class ChatRequest(BaseModel):
    messages: list[dict]
    model: str = "MiniMax-M3"


class ChatResponse(BaseModel):
    content: str
    model: str


@router.post("/chat", response_model=ChatResponse)
def chat_endpoint(request: ChatRequest):
    content = chat(messages=request.messages, model=request.model)
    return ChatResponse(content=content, model=request.model)
