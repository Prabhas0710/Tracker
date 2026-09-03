from __future__ import annotations

from typing import Any, Optional, TypedDict


class ExpenseGraphState(TypedDict, total=False):
    user_id: int
    db_transaction_id: int
    amount: float
    merchant: Optional[str]
    raw_texts: list[str]
    sources: list[str]
    direction: str
    memory_hit: Optional[dict[str, Any]]
    prior_hit: Optional[dict[str, Any]]
    preference: Optional[str]
    category: Optional[str]
    subcategory: Optional[str]
    description: Optional[str]
    confidence: float
    needs_user: bool
    user_response: Optional[str]
    clarification_message: Optional[str]
    clarification_id: Optional[int]
    expense_id: Optional[int]
    dashboard_summary: Optional[dict[str, Any]]
    message: Optional[str]
    error: Optional[str]
    classification_source: Optional[str]
