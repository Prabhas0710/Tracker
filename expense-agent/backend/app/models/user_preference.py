from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.database import Base

if TYPE_CHECKING:
    from app.models.transaction import Transaction
    from app.models.user import User


class MerchantMemory(Base):
    __tablename__ = "merchant_memories"
    __table_args__ = (UniqueConstraint("user_id", "merchant_key", name="uq_user_merchant"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    merchant_key: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    merchant_display: Mapped[str] = mapped_column(String(255), nullable=False)
    category: Mapped[str] = mapped_column(String(80), nullable=False)
    subcategory: Mapped[Optional[str]] = mapped_column(String(80), nullable=True)
    confidence: Mapped[float] = mapped_column(Float, default=0.95)
    hit_count: Mapped[int] = mapped_column(Integer, default=1)
    is_seed_prior: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    user: Mapped["User"] = relationship(back_populates="merchant_memories")


class UserPreference(Base):
    __tablename__ = "user_preferences"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    key: Mapped[str] = mapped_column(String(120), nullable=False)
    value: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    user: Mapped["User"] = relationship(back_populates="preferences")


class ClarificationRequest(Base):
    __tablename__ = "clarification_requests"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    transaction_id: Mapped[int] = mapped_column(ForeignKey("transactions.id"), unique=True)
    prompt_message: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="pending")
    proposed_category: Mapped[Optional[str]] = mapped_column(String(80), nullable=True)
    proposed_subcategory: Mapped[Optional[str]] = mapped_column(String(80), nullable=True)
    proposed_description: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    user_response: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    graph_thread_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    transaction: Mapped["Transaction"] = relationship(back_populates="clarification")


class ChatConversation(Base):
    __tablename__ = "chat_conversations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False, default="New chat")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    messages: Mapped[list["ChatMessage"]] = relationship(
        back_populates="conversation",
        cascade="all, delete-orphan",
        order_by="ChatMessage.id",
    )


class ChatMessage(Base):
    __tablename__ = "chat_messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    conversation_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("chat_conversations.id"), nullable=True, index=True
    )
    role: Mapped[str] = mapped_column(String(32), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    clarification_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("clarification_requests.id"), nullable=True
    )
    expense_id: Mapped[Optional[int]] = mapped_column(ForeignKey("expenses.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    conversation: Mapped[Optional["ChatConversation"]] = relationship(back_populates="messages")


class MerchantPrior(Base):
    __tablename__ = "merchant_priors"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    merchant_key: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    merchant_display: Mapped[str] = mapped_column(String(255), nullable=False)
    category: Mapped[str] = mapped_column(String(80), nullable=False)
    subcategory: Mapped[Optional[str]] = mapped_column(String(80), nullable=True)
    confidence: Mapped[float] = mapped_column(Float, default=0.92)
