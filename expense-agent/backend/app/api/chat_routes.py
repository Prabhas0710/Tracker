from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.agents.expense_agent import ExpenseAgent
from app.database.database import get_db
from app.schemas.chat_schema import (
    ChatBriefingOut,
    ChatConversationDetail,
    ChatConversationOut,
    ChatRequest,
    ChatResponse,
    ClarificationOut,
    ConfirmRequest,
)
from app.services.assistant_service import AssistantService
from app.services.briefing_service import BriefingService
from app.services.chat_history_service import ChatHistoryService
from app.services.notification_service import NotificationService

router = APIRouter(prefix="/api", tags=["chat"])


@router.post("/chat", response_model=ChatResponse)
def chat(payload: ChatRequest, db: Session = Depends(get_db)):
    return ExpenseAgent(db).handle_chat(
        payload.message,
        clarification_id=payload.clarification_id,
        conversation_id=payload.conversation_id,
    )


@router.get("/chat/history")
def chat_history(conversation_id: int | None = None, db: Session = Depends(get_db)):
    return AssistantService(db).history(conversation_id=conversation_id)


@router.get("/chat/conversations", response_model=list[ChatConversationOut])
def list_chat_conversations(db: Session = Depends(get_db)):
    return ChatHistoryService(db).list_conversations()


@router.get("/chat/conversations/{conversation_id}", response_model=ChatConversationDetail)
def get_chat_conversation(conversation_id: int, db: Session = Depends(get_db)):
    detail = ChatHistoryService(db).get_conversation(conversation_id)
    if not detail:
        raise HTTPException(status_code=404, detail="Chat not found")
    return detail


@router.delete("/chat/conversations/{conversation_id}")
def delete_chat_conversation(conversation_id: int, db: Session = Depends(get_db)):
    if not ChatHistoryService(db).delete_conversation(conversation_id):
        raise HTTPException(status_code=404, detail="Chat not found")
    return {"deleted": True}


@router.get("/chat/briefing", response_model=ChatBriefingOut)
def chat_briefing(db: Session = Depends(get_db)):
    message = BriefingService(db).ensure_daily_briefing()
    return ChatBriefingOut(message=message, shown=message is not None)


@router.get("/notifications/pending", response_model=list[ClarificationOut])
def pending_notifications(db: Session = Depends(get_db)):
    rows = NotificationService(db).list_pending()
    db.commit()
    return rows


@router.post("/clarifications/{clarification_id}/confirm", response_model=ChatResponse)
def confirm_clarification(
    clarification_id: int, payload: ConfirmRequest, db: Session = Depends(get_db)
):
    service = NotificationService(db)
    if not service.get(clarification_id):
        raise HTTPException(status_code=404, detail="Clarification not found")
    return ExpenseAgent(db).confirm_clarification(
        clarification_id,
        confirmed=payload.confirmed,
        category=payload.category,
        subcategory=payload.subcategory,
        description=payload.description,
    )
