from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1)
    clarification_id: Optional[int] = None
    conversation_id: Optional[int] = None


class ChatResponse(BaseModel):
    reply: str
    clarification_id: Optional[int] = None
    expense_id: Optional[int] = None
    conversation_id: Optional[int] = None
    needs_confirm: bool = False
    proposed: Optional[dict[str, Any]] = None
    dashboard_hint: Optional[dict[str, Any]] = None


class ChatMessageOut(BaseModel):
    role: str
    content: str
    created_at: Optional[datetime] = None


class ChatConversationOut(BaseModel):
    id: int
    title: str
    preview: str = ""
    created_at: datetime
    updated_at: datetime
    message_count: int = 0


class ChatConversationDetail(ChatConversationOut):
    messages: list[ChatMessageOut] = Field(default_factory=list)


class ChatBriefingOut(BaseModel):
    message: Optional[str] = None
    shown: bool = False


class ClarificationOut(BaseModel):
    id: int
    transaction_id: int
    prompt_message: str
    status: str
    amount: Optional[float] = None
    merchant: Optional[str] = None
    expense_id: Optional[int] = None
    current_category: Optional[str] = None
    proposed_category: Optional[str] = None
    proposed_subcategory: Optional[str] = None
    proposed_description: Optional[str] = None
    user_response: Optional[str] = None
    created_at: datetime

    model_config = {"from_attributes": True}


class ConfirmRequest(BaseModel):
    confirmed: bool = True
    category: Optional[str] = None
    subcategory: Optional[str] = None
    description: Optional[str] = None
