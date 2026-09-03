"""Pending clarification queue."""

from __future__ import annotations

from typing import Optional

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import ClarificationRequest, Transaction
from app.schemas.chat_schema import ClarificationOut
from app.services.expense_service import ExpenseService


class NotificationService:
    def __init__(self, db: Session):
        self.db = db
        self.settings = get_settings()

    def _ensure_other_expense(self, txn: Transaction, row: ClarificationRequest) -> None:
        """Older pending items may lack an expense — land them as Other."""
        if txn.expense:
            return
        ExpenseService(self.db).save_from_transaction(
            txn,
            category="Other",
            subcategory="Unknown",
            description=row.proposed_description
            or (f"Uncategorized · {txn.merchant}" if txn.merchant else "Uncategorized payment"),
            confidence=0.0,
            source="auto",
            direction=getattr(txn, "direction", None) or "debit",
        )
        row.status = "pending"
        txn.status = "needs_user"
        self.db.flush()

    def list_pending(self, user_id: Optional[int] = None) -> list[ClarificationOut]:
        user_id = user_id or self.settings.default_user_id
        rows = (
            self.db.query(ClarificationRequest)
            .filter(
                ClarificationRequest.user_id == user_id,
                ClarificationRequest.status == "pending",
            )
            .order_by(ClarificationRequest.created_at.desc())
            .all()
        )
        results: list[ClarificationOut] = []
        for row in rows:
            txn = self.db.get(Transaction, row.transaction_id)
            if txn:
                self._ensure_other_expense(txn, row)
            expense = txn.expense if txn else None
            results.append(
                ClarificationOut(
                    id=row.id,
                    transaction_id=row.transaction_id,
                    prompt_message=row.prompt_message,
                    status=row.status,
                    amount=float(txn.amount) if txn else None,
                    merchant=txn.merchant if txn else None,
                    expense_id=expense.id if expense else None,
                    current_category=expense.category if expense else "Other",
                    proposed_category=row.proposed_category,
                    proposed_subcategory=row.proposed_subcategory,
                    proposed_description=row.proposed_description,
                    user_response=row.user_response,
                    created_at=row.created_at,
                )
            )
        return results

    def get(self, clarification_id: int, user_id: Optional[int] = None) -> Optional[ClarificationRequest]:
        user_id = user_id or self.settings.default_user_id
        return (
            self.db.query(ClarificationRequest)
            .filter(
                ClarificationRequest.id == clarification_id,
                ClarificationRequest.user_id == user_id,
            )
            .first()
        )
