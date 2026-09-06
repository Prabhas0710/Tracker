"""Credit card bill / mark-as-paid routes."""

from datetime import datetime
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.database.database import get_db
from app.services.credit_card_cycle_service import (
    SUPPORTED_BANKS,
    CreditCardCycleService,
    normalize_card_bank,
)

router = APIRouter(prefix="/api/credit-cards", tags=["credit-cards"])

CardBankPath = Literal["ICICI", "HDFC", "icici", "hdfc"]


class MarkPaidBody(BaseModel):
    paid_at: Optional[datetime] = None
    amount: Optional[float] = Field(default=None, ge=0)


@router.post("/{bank}/mark-paid")
def mark_credit_card_paid(
    bank: CardBankPath,
    body: MarkPaidBody = MarkPaidBody(),
    db: Session = Depends(get_db),
):
    normalized = normalize_card_bank(bank)
    if not normalized or normalized not in SUPPORTED_BANKS:
        raise HTTPException(status_code=400, detail="Bank must be ICICI or HDFC")

    settings = get_settings()
    try:
        result = CreditCardCycleService(db).mark_bill_paid(
            normalized,
            user_id=settings.default_user_id,
            paid_at=body.paid_at,
            amount=body.amount,
        )
        db.commit()
        return result
    except Exception as exc:  # noqa: BLE001
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
