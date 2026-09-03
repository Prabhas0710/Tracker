"""LangGraph expense classification workflow."""

from __future__ import annotations

from functools import partial
from typing import Any, Callable, Optional

from langgraph.graph import END, StateGraph
from sqlalchemy.orm import Session

from app.graph import nodes
from app.graph.state import ExpenseGraphState


def _bind(fn: Callable, db: Session) -> Callable[[ExpenseGraphState], ExpenseGraphState]:
    return partial(fn, db=db)


def build_expense_graph(db: Session):
    graph = StateGraph(ExpenseGraphState)

    graph.add_node("receive_transaction", _bind(nodes.receive_transaction, db))
    graph.add_node("normalize_transaction", _bind(nodes.normalize_transaction, db))
    graph.add_node("correlate_payment_sources", _bind(nodes.correlate_payment_sources, db))
    graph.add_node("lookup_memory", _bind(nodes.lookup_memory, db))
    graph.add_node("classify_category", _bind(nodes.classify_category, db))
    graph.add_node("check_confidence", _bind(nodes.check_confidence, db))
    graph.add_node("ask_user", _bind(nodes.ask_user, db))
    graph.add_node("process_user_response", _bind(nodes.process_user_response, db))
    graph.add_node("learn_preference", _bind(nodes.learn_preference, db))
    graph.add_node("save_expense", _bind(nodes.save_expense, db))
    graph.add_node("update_dashboard", _bind(nodes.update_dashboard, db))

    graph.set_entry_point("receive_transaction")
    graph.add_edge("receive_transaction", "normalize_transaction")
    graph.add_edge("normalize_transaction", "correlate_payment_sources")
    graph.add_edge("correlate_payment_sources", "lookup_memory")
    graph.add_edge("lookup_memory", "classify_category")
    graph.add_edge("classify_category", "check_confidence")
    graph.add_conditional_edges(
        "check_confidence",
        nodes.route_after_confidence,
        {
            "save_expense": "save_expense",
            "ask_user": "ask_user",
        },
    )
    graph.add_conditional_edges(
        "ask_user",
        nodes.route_after_ask,
        {
            "process_user_response": "process_user_response",
            "__end__": END,
        },
    )
    graph.add_edge("process_user_response", "learn_preference")
    graph.add_edge("learn_preference", "save_expense")
    graph.add_edge("save_expense", "update_dashboard")
    graph.add_edge("update_dashboard", END)

    return graph.compile()


def run_classification(db: Session, transaction_id: int, user_response: Optional[str] = None) -> dict[str, Any]:
    app = build_expense_graph(db)
    initial: ExpenseGraphState = {
        "db_transaction_id": transaction_id,
        "confidence": 0.0,
        "needs_user": False,
    }
    if user_response:
        initial["user_response"] = user_response
    return app.invoke(initial)


def resume_after_user_response(
    db: Session,
    transaction_id: int,
    user_response: str,
    clarification_id: Optional[int] = None,
) -> dict[str, Any]:
    """Resume from process_user_response → learn → save → dashboard."""
    from app.graph.nodes import (
        learn_preference,
        process_user_response,
        save_expense,
        update_dashboard,
    )
    from app.models import Transaction

    txn = db.get(Transaction, transaction_id)
    if not txn:
        raise ValueError("Transaction not found")

    state: ExpenseGraphState = {
        "db_transaction_id": transaction_id,
        "user_id": txn.user_id,
        "amount": float(txn.amount),
        "merchant": txn.merchant,
        "raw_texts": list(txn.raw_texts or []),
        "sources": list(txn.sources or []),
        "user_response": user_response,
        "clarification_id": clarification_id
        or (txn.clarification.id if txn.clarification else None),
        "needs_user": False,
        "confidence": 0.0,
    }
    state = process_user_response(state, db)
    state = learn_preference(state, db)
    state = save_expense(state, db)
    state = update_dashboard(state, db)
    return dict(state)
