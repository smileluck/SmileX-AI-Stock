from fastapi import APIRouter
from pydantic import BaseModel

from app.services.llm import chat, get_model_for_function as _resolve_model

router = APIRouter(prefix="/ai", tags=["ai"])


class ChatRequest(BaseModel):
    messages: list[dict]
    model: str | None = None


class ChatResponse(BaseModel):
    content: str
    model: str


@router.post("/chat", response_model=ChatResponse)
def chat_endpoint(request: ChatRequest):
    content = chat(messages=request.messages, model=request.model)
    used_model = request.model or _resolve_model("chat")
    return ChatResponse(content=content, model=used_model)
