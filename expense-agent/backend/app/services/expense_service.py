"""Expense CRUD and DB-backed tools for agents."""

from __future__ import annotations

from calendar import monthrange
from datetime import datetime, timezone
from typing import Any, Optional
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import Expense, Transaction
from app.schemas.expense_schema import ExpenseCreate, ExpenseOut, ExpenseUpdate
from app.services.bank_email_parser import detect_credit_card_issuer

IST = ZoneInfo("Asia/Kolkata")


class ExpenseService:
    def __init__(self, db: Session):
        self.db = db
        self.settings = get_settings()

    def create(self, payload: ExpenseCreate, user_id: Optional[int] = None, source: str = "manual") -> Expense:
        user_id = user_id or self.settings.default_user_id
        expense = Expense(
            user_id=user_id,
            amount=payload.amount,
            merchant=payload.merchant,
            category=payload.category,
            subcategory=payload.subcategory,
            description=payload.description,
            confidence=1.0,
            source=source,
            spent_at=payload.spent_at or datetime.now(timezone.utc),
        )
        self.db.add(expense)
        self.db.flush()
        return expense

    def save_from_transaction(
        self,
        txn: Transaction,
        *,
        category: str,
        subcategory: Optional[str],
        description: Optional[str],
        confidence: float,
        source: str = "auto",
        direction: str = "debit",
    ) -> Expense:
        if direction not in {"debit", "credit", "transfer"}:
            direction = "debit"
        if txn.expense:
            expense = txn.expense
            expense.category = category
            expense.subcategory = subcategory
            expense.description = description
            expense.confidence = confidence
            expense.merchant = txn.merchant
            expense.amount = txn.amount
            expense.direction = direction
        else:
            expense = Expense(
                user_id=txn.user_id,
                transaction_id=txn.id,
                amount=txn.amount,
                merchant=txn.merchant,
                category=category,
                subcategory=subcategory,
                description=description,
                confidence=confidence,
                source=source,
                direction=direction,
                spent_at=txn.event_timestamp,
            )
            self.db.add(expense)
        txn.direction = direction
        txn.status = "saved"
        self.db.flush()
        return expense

    def list_expenses(
        self,
        user_id: Optional[int] = None,
        *,
        limit: int = 500,
        year: Optional[int] = None,
        month: Optional[int] = None,
    ) -> list[ExpenseOut]:
        user_id = user_id or self.settings.default_user_id
        query = self.db.query(Expense).filter(Expense.user_id == user_id)
        if year is not None and month is not None:
            start = datetime(year, month, 1, tzinfo=IST)
            last_day = monthrange(year, month)[1]
            end = datetime(year, month, last_day, 23, 59, 59, tzinfo=IST)
            query = query.filter(Expense.spent_at >= start, Expense.spent_at <= end)
        rows = query.order_by(Expense.spent_at.desc()).limit(limit).all()
        return [self.to_out(r) for r in rows]

    def get(self, expense_id: int, user_id: Optional[int] = None) -> Optional[Expense]:
        user_id = user_id or self.settings.default_user_id
        return (
            self.db.query(Expense)
            .filter(Expense.id == expense_id, Expense.user_id == user_id)
            .first()
        )

    def update(self, expense_id: int, payload: ExpenseUpdate, user_id: Optional[int] = None) -> Optional[Expense]:
        expense = self.get(expense_id, user_id=user_id)
        if not expense:
            return None
        data = payload.model_dump(exclude_unset=True)
        category_touched = "category" in data or "subcategory" in data or "direction" in data
        for key, value in data.items():
            setattr(expense, key, value)
        if "direction" in data and expense.transaction_id:
            txn = self.db.get(Transaction, expense.transaction_id)
            if txn:
                txn.direction = expense.direction
        if category_touched and expense.merchant and expense.category:
            from app.agents.memory_agent import MemoryAgent

            MemoryAgent(self.db).learn(
                merchant=expense.merchant,
                category=expense.category,
                subcategory=expense.subcategory,
                confidence=1.0,
                user_id=expense.user_id,
            )
            expense.confidence = 1.0
            if expense.transaction_id:
                txn = self.db.get(Transaction, expense.transaction_id)
                if txn:
                    txn.status = "saved"
                    if txn.clarification and txn.clarification.status in {"pending", "answered"}:
                        txn.clarification.status = "confirmed"
                        txn.clarification.proposed_category = expense.category
                        txn.clarification.proposed_subcategory = expense.subcategory
        if category_touched and expense.category:
            from app.services.category_service import CategoryService

            CategoryService(self.db).ensure(expense.category)
        self.db.flush()
        return expense

    def _reference_for(self, expense: Expense) -> tuple[Optional[str], Optional[str]]:
        txn = expense.transaction
        if not txn and expense.transaction_id:
            txn = self.db.get(Transaction, expense.transaction_id)
        if not txn:
            return None, None
        upi = txn.upi_ref or None
        external = txn.external_transaction_id or None
        # Prefer real UPI / bank ref over synthetic fingerprints like "cc_bill_payment:..."
        ref = upi or external
        if ref and ":" in str(ref) and not str(ref).startswith("upi:"):
            # Keep fingerprint only if nothing better exists
            pass
        if isinstance(ref, str) and ref.startswith("upi:"):
            ref = ref.split(":", 1)[1]
        return upi, ref

    def _card_meta_for(self, txn: Optional[Transaction]) -> tuple[Optional[str], Optional[str]]:
        if not txn or (txn.payment_method or "").lower() != "credit card":
            return None, None
        issuer: Optional[str] = None
        for raw in txn.raw_texts or []:
            found = detect_credit_card_issuer(str(raw))
            if found:
                issuer = found
                break
        return issuer, txn.account_suffix

    def to_out(self, expense: Expense) -> ExpenseOut:
        upi_ref, reference_id = self._reference_for(expense)
        txn = expense.transaction
        if not txn and expense.transaction_id:
            txn = self.db.get(Transaction, expense.transaction_id)
        card_issuer, account_suffix = self._card_meta_for(txn)
        data = ExpenseOut.model_validate(expense).model_dump()
        data["upi_ref"] = upi_ref
        data["reference_id"] = reference_id
        data["payment_method"] = txn.payment_method if txn else None
        data["card_issuer"] = card_issuer
        data["account_suffix"] = account_suffix
        return ExpenseOut(**data)
