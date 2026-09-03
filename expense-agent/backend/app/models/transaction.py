from datetime import datetime
from typing import TYPE_CHECKING, Any, Optional

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, Numeric, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.database import Base

if TYPE_CHECKING:
    from app.models.expense import Expense
    from app.models.user_preference import ClarificationRequest


class PaymentEvent(Base):
    __tablename__ = "payment_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, default=1)
    source: Mapped[str] = mapped_column(String(64), nullable=False)
    amount: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
    merchant: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    payment_method: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    transaction_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True, index=True)
    upi_ref: Mapped[Optional[str]] = mapped_column(String(128), nullable=True, index=True)
    account_suffix: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    raw_text: Mapped[str] = mapped_column(Text, nullable=False)
    event_timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    payload_json: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON, nullable=True)
    correlated_transaction_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("transactions.id"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    transaction: Mapped[Optional["Transaction"]] = relationship(back_populates="payment_events")


class Transaction(Base):
    __tablename__ = "transactions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, default=1)
    amount: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
    merchant: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    payment_method: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    external_transaction_id: Mapped[Optional[str]] = mapped_column(
        String(128), nullable=True, index=True
    )
    upi_ref: Mapped[Optional[str]] = mapped_column(String(128), nullable=True, index=True)
    sources: Mapped[list] = mapped_column(JSON, default=list)
    status: Mapped[str] = mapped_column(String(32), default="pending", index=True)
    direction: Mapped[str] = mapped_column(String(16), default="debit", index=True)  # debit | credit
    event_timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    raw_texts: Mapped[list] = mapped_column(JSON, default=list)
    account_suffix: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    payment_events: Mapped[list["PaymentEvent"]] = relationship(back_populates="transaction")
    expense: Mapped[Optional["Expense"]] = relationship(back_populates="transaction", uselist=False)
    clarification: Mapped[Optional["ClarificationRequest"]] = relationship(
        back_populates="transaction", uselist=False
    )
