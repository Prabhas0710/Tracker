"""Expense tools — DB is the source of truth for amounts."""

from __future__ import annotations

from typing import Any, Optional

from sqlalchemy.orm import Session

from app.services.expense_service import ExpenseService


def list_recent_expenses(db: Session, limit: int = 20) -> list[dict[str, Any]]:
    expenses = ExpenseService(db).list_expenses(limit=limit)
    return [e.model_dump() for e in expenses]


def get_expense(db: Session, expense_id: int) -> Optional[dict[str, Any]]:
    expense = ExpenseService(db).get(expense_id)
    return ExpenseService(db).to_out(expense).model_dump() if expense else None
