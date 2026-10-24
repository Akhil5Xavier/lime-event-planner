from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.assistant import agent
from app.assistant.llm import LLMError
from app.config import Settings, get_settings
from app.db import get_db
from app.schemas import ChatIn, ChatOut, ChatStatus
from app.security import get_current_user

router = APIRouter(prefix="/api/chat", tags=["assistant"], dependencies=[Depends(get_current_user)])


@router.get("/status", response_model=ChatStatus)
def chat_status(settings: Settings = Depends(get_settings)):
    return ChatStatus(enabled=settings.llm_enabled, provider=settings.llm_provider, model=settings.llm_model)


@router.post("", response_model=ChatOut)
def chat(body: ChatIn, db: Session = Depends(get_db), settings: Settings = Depends(get_settings)):
    """Answer the last question in the conversation, looking up event data as needed (read-only)."""
    if not settings.llm_enabled:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                            detail="The AI assistant is not configured. An admin needs to set LLM_API_KEY.")
    try:
        result = agent.answer(db, settings, [m.model_dump() for m in body.messages])
    except LLMError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc))
    return ChatOut(reply=result.reply, tools_used=result.tools_used)
