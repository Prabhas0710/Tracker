from datetime import datetime
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field


PaymentSource = Literal[
    "upi_notification",
    "bank_sms",
    "email",
    "webhook",
    "manual",
    "forwarded",
    "mock",
]


class PaymentEventIn(BaseModel):
    source: PaymentSource
    amount: Optional[float] = None
    merchant: Optional[str] = None
    payment_method: Optional[str] = "UPI"
    transaction_id: Optional[str] = None
    upi_ref: Optional[str] = None
    account_suffix: Optional[str] = None
    timestamp: Optional[datetime] = None
    raw_text: str
    payload: Optional[dict[str, Any]] = None


class PaymentEventNormalized(BaseModel):
    source: str
    amount: float
    merchant: Optional[str] = None
    payment_method: Optional[str] = "UPI"
    transaction_id: Optional[str] = None
    upi_ref: Optional[str] = None
    account_suffix: Optional[str] = None
    timestamp: datetime
    raw_text: str
    payload: Optional[dict[str, Any]] = None


class MockPaymentRequest(BaseModel):
    """Dev helper: accept structured fields and/or raw_text."""

    source: PaymentSource = "upi_notification"
    amount: Optional[float] = None
    merchant: Optional[str] = None
    payment_method: Optional[str] = "UPI"
    transaction_id: Optional[str] = None
    upi_ref: Optional[str] = None
    account_suffix: Optional[str] = None
    timestamp: Optional[datetime] = None
    raw_text: str = Field(..., min_length=1)


class MockPaymentPairRequest(BaseModel):
    upi: MockPaymentRequest
    sms: MockPaymentRequest


class TransactionOut(BaseModel):
    id: int
    amount: float
    merchant: Optional[str]
    payment_method: Optional[str]
    external_transaction_id: Optional[str]
    upi_ref: Optional[str]
    sources: list[str]
    status: str
    event_timestamp: datetime
    raw_texts: list[str]
    expense_id: Optional[int] = None
    clarification_id: Optional[int] = None
    category: Optional[str] = None
    subcategory: Optional[str] = None
    confidence: Optional[float] = None
    message: Optional[str] = None

    model_config = {"from_attributes": True}


class IngestResult(BaseModel):
    transaction: TransactionOut
    created_new: bool
    merged: bool
    classification: Optional[dict[str, Any]] = None
