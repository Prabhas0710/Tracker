from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field


class ExpenseCreate(BaseModel):
    amount: float = Field(gt=0)
    category: str
    subcategory: Optional[str] = None
    description: Optional[str] = None
    merchant: Optional[str] = None
    spent_at: Optional[datetime] = None


class ExpenseUpdate(BaseModel):
    category: Optional[str] = None
    subcategory: Optional[str] = None
    description: Optional[str] = None
    merchant: Optional[str] = None
    direction: Optional[Literal["debit", "credit", "transfer"]] = None


class ExpenseOut(BaseModel):
    id: int
    amount: float
    merchant: Optional[str]
    category: str
    subcategory: Optional[str]
    description: Optional[str]
    confidence: Optional[float]
    source: str
    direction: str = "debit"
    spent_at: datetime
    transaction_id: Optional[int] = None
    upi_ref: Optional[str] = None
    reference_id: Optional[str] = None
    payment_method: Optional[str] = None
    card_issuer: Optional[str] = None
    account_suffix: Optional[str] = None
    created_at: datetime

    model_config = {"from_attributes": True}


class ManualExpenseNL(BaseModel):
    text: str = Field(..., min_length=1, examples=["Spent ₹500 on movie"])
