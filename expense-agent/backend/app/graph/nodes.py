"""LangGraph node implementations for the expense workflow."""

from __future__ import annotations

from typing import Any, Literal

from sqlalchemy.orm import Session

from app.agents.category_agent import CategoryAgent
from app.agents.memory_agent import MemoryAgent
from app.agents.notification_agent import NotificationAgent
from app.lib.categories_match import is_weak_category, looks_like_person_payee
from app.lib.receiver_classify import classify_receiver
from app.core.logging import get_logger
from app.graph.state import ExpenseGraphState
from app.models import ClarificationRequest, Transaction
from app.services.analytics_service import AnalyticsService
from app.services.expense_service import ExpenseService

logger = get_logger(__name__)


def _get_txn(db: Session, txn_id: int) -> Transaction:
    txn = db.get(Transaction, txn_id)
    if not txn:
        raise ValueError(f"Transaction {txn_id} not found")
    return txn


def receive_transaction(state: ExpenseGraphState, db: Session) -> ExpenseGraphState:
    txn = _get_txn(db, state["db_transaction_id"])
    return {
        **state,
        "user_id": txn.user_id,
        "amount": float(txn.amount),
        "merchant": txn.merchant,
        "raw_texts": list(txn.raw_texts or []),
        "sources": list(txn.sources or []),
        "direction": getattr(txn, "direction", None) or "debit",
    }


def normalize_transaction(state: ExpenseGraphState, db: Session) -> ExpenseGraphState:
    # Already normalized at ingest; ensure merchant/amount present
    txn = _get_txn(db, state["db_transaction_id"])
    return {
        **state,
        "amount": float(txn.amount),
        "merchant": txn.merchant or state.get("merchant"),
        "raw_texts": list(txn.raw_texts or state.get("raw_texts") or []),
        "sources": list(txn.sources or state.get("sources") or []),
    }


def correlate_payment_sources(state: ExpenseGraphState, db: Session) -> ExpenseGraphState:
    txn = _get_txn(db, state["db_transaction_id"])
    # Correlation already done in TransactionService; expose combined context
    return {
        **state,
        "sources": list(txn.sources or []),
        "raw_texts": list(txn.raw_texts or []),
        "merchant": txn.merchant,
    }


def lookup_memory(state: ExpenseGraphState, db: Session) -> ExpenseGraphState:
    memory_agent = MemoryAgent(db)
    result = memory_agent.lookup(state.get("merchant"), user_id=state.get("user_id"))
    return {
        **state,
        "memory_hit": result.get("memory"),
        "prior_hit": result.get("prior"),
        "preference": result.get("preference"),
    }


def classify_category(state: ExpenseGraphState, db: Session) -> ExpenseGraphState:
    # If resuming with user_response, skip auto classify here
    if state.get("user_response"):
        return state

    from app.services.bank_email_parser import strip_credit_limit_suffix
    from app.services.self_transfer import is_self_transfer_merchant, self_transfer_classification

    merchant = state.get("merchant")
    if merchant:
        cleaned = strip_credit_limit_suffix(merchant)
        if cleaned and cleaned != merchant:
            merchant = cleaned
            txn = _get_txn(db, state["db_transaction_id"])
            txn.merchant = cleaned
            if txn.expense and txn.expense.merchant:
                txn.expense.merchant = strip_credit_limit_suffix(txn.expense.merchant)
            db.flush()

    # Self UPI / own-name transfers are not spending or income
    if is_self_transfer_merchant(merchant):
        classified = self_transfer_classification(merchant)
        return {
            **state,
            "merchant": merchant,
            **classified,
            "needs_user": False,
        }

    # Bank credit alerts are income — do not ask the user
    if (state.get("direction") or "debit") == "credit":
        return {
            **state,
            "merchant": merchant,
            "category": "Income",
            "subcategory": "UPI Credit",
            "description": f"Credited from {merchant}" if merchant else "Amount credited",
            "confidence": 0.98,
            "classification_source": "bank_credit",
        }

    agent = CategoryAgent(db)
    result = agent.classify(
        merchant=merchant,
        raw_texts=list(state.get("raw_texts") or []),
        memory=state.get("memory_hit"),
        prior=state.get("prior_hit"),
        preference=state.get("preference"),
    )
    category = result.get("category")
    subcategory = result.get("subcategory")
    description = result.get("description")
    confidence = float(result.get("confidence", 0.0))
    source = result.get("source")
    if category == "Credit Card":
        category = "Other"
        subcategory = subcategory if subcategory and subcategory != "Card Spend" else "Unknown"
    if isinstance(category, str) and category.lower() == "personal":
        category = "Personal"

    # Person-to-person UPI cannot be inferred from the receiver — Personal unless the user already taught us.
    if looks_like_person_payee(merchant) and source not in {"memory", "preference", "user_nl"}:
        category = "Personal"
        subcategory = None
        description = merchant or "Payment"
        confidence = 0.85
        source = "person_personal"

    # Receiver VPA can still override a weak/unknown guess (airtel-prepaid → Recharge).
    if is_weak_category(category) or not category:
        receiver = classify_receiver(merchant, list(state.get("raw_texts") or []))
        if receiver:
            category = receiver["category"]
            subcategory = receiver.get("subcategory")
            description = receiver.get("description") or description
            confidence = float(receiver.get("confidence") or 0.9)
            source = receiver.get("source")
        else:
            category = "Personal"
            subcategory = None
            description = merchant or "Payment"
            confidence = max(confidence, 0.8)
            source = source or "fallback"

    return {
        **state,
        "merchant": merchant,
        "category": category,
        "subcategory": subcategory,
        "description": description,
        "confidence": confidence,
        "classification_source": source,
    }


def check_confidence(state: ExpenseGraphState, db: Session) -> ExpenseGraphState:
    # Always auto-save. Receiver VPA/merchant maps to a category;
    # anything the bot cannot decide is Personal.
    if state.get("classification_source") in {"self_transfer", "bank_credit"}:
        confidence = max(float(state.get("confidence") or 0.0), 0.99)
    else:
        confidence = float(state.get("confidence") or 0.0)
        category = state.get("category")
        if is_weak_category(category) or not category:
            confidence = max(confidence, 0.8)
            state = {
                **state,
                "category": "Personal",
                "subcategory": None,
                "confidence": confidence,
                "classification_source": state.get("classification_source") or "fallback",
            }
    txn = _get_txn(db, state["db_transaction_id"])
    txn.status = "classified"
    db.flush()
    return {**state, "needs_user": False, "confidence": confidence}


def route_after_confidence(state: ExpenseGraphState) -> Literal["save_expense", "ask_user"]:
    if state.get("needs_user"):
        return "ask_user"
    return "save_expense"


def ask_user(state: ExpenseGraphState, db: Session) -> ExpenseGraphState:
    notif = NotificationAgent()
    prompt = notif.clarification_prompt(
        amount=float(state["amount"]),
        merchant=state.get("merchant"),
    )
    txn = _get_txn(db, state["db_transaction_id"])
    direction = state.get("direction") or getattr(txn, "direction", None) or "debit"
    guessed = state.get("category") or "Other"
    guessed_sub = state.get("subcategory") or "Unknown"

    clarification = txn.clarification
    if not clarification:
        clarification = ClarificationRequest(
            user_id=state.get("user_id") or txn.user_id,
            transaction_id=txn.id,
            prompt_message=prompt,
            status="pending",
            graph_thread_id=str(txn.id),
            proposed_category=guessed,
            proposed_subcategory=guessed_sub,
            proposed_description=state.get("description"),
        )
        db.add(clarification)
    else:
        clarification.prompt_message = prompt
        clarification.status = "pending"
        clarification.proposed_category = guessed
        clarification.proposed_subcategory = guessed_sub
        if state.get("description"):
            clarification.proposed_description = state.get("description")

    ledger_category = "Needs you"
    ledger_sub = "Unknown"
    ledger_desc = state.get("description") or (
        f"Uncategorized · {txn.merchant}" if txn.merchant else "Uncategorized payment"
    )

    ExpenseService(db).save_from_transaction(
        txn,
        category=ledger_category,
        subcategory=ledger_sub,
        description=ledger_desc,
        confidence=float(state.get("confidence") or 0.0),
        source="auto",
        direction=direction,
    )
    clarification.status = "pending"
    txn.status = "needs_user"
    db.flush()
    try:
        from app.services.push_service import PushService
        from app.services.voice_service import VoiceService

        body = VoiceService(db).question_for(
            amount=float(state["amount"]),
            merchant=state.get("merchant") or txn.merchant,
        )
        sent = PushService(db).notify_payment(
            title="Ledgerly",
            body=body,
            user_id=state.get("user_id") or txn.user_id,
            clarification_id=clarification.id,
        )
        if sent:
            logger.info("Push sent to %s device(s) for txn %s", sent, txn.id)
        else:
            logger.warning("No push delivered for txn %s — phone must tap Allow alerts", txn.id)
    except Exception as extra:  # noqa: BLE001
        logger.warning("Push after ask_user failed: %s", extra)
    return {
        **state,
        "category": ledger_category,
        "subcategory": ledger_sub,
        "clarification_message": prompt,
        "clarification_id": clarification.id,
        "expense_id": txn.expense.id if txn.expense else None,
        "message": prompt,
        "needs_user": True,
    }


def process_user_response(state: ExpenseGraphState, db: Session) -> ExpenseGraphState:
    user_text = state.get("user_response") or ""
    agent = CategoryAgent(db)
    parsed = agent.parse_user_response(
        user_text,
        merchant=state.get("merchant"),
        amount=state.get("amount"),
    )
    clarification_id = state.get("clarification_id")
    if clarification_id:
        clarification = db.get(ClarificationRequest, clarification_id)
        if clarification:
            clarification.user_response = user_text
            clarification.proposed_category = parsed.get("category")
            clarification.proposed_subcategory = parsed.get("subcategory")
            clarification.proposed_description = parsed.get("description")
            clarification.status = "answered"
            db.flush()

    confirm = NotificationAgent().confirmation_prompt(
        amount=float(state["amount"]),
        category=parsed.get("category") or "Other",
        subcategory=parsed.get("subcategory"),
        description=parsed.get("description"),
        merchant=state.get("merchant"),
    )
    return {
        **state,
        "category": parsed.get("category"),
        "subcategory": parsed.get("subcategory"),
        "description": parsed.get("description"),
        "confidence": float(parsed.get("confidence", 0.93)),
        "classification_source": parsed.get("source"),
        "needs_user": False,
        "message": confirm,
    }


def learn_preference(state: ExpenseGraphState, db: Session) -> ExpenseGraphState:
    if not state.get("category"):
        return state
    MemoryAgent(db).learn(
        merchant=state.get("merchant"),
        category=state["category"],
        subcategory=state.get("subcategory"),
        confidence=max(float(state.get("confidence") or 0.95), 0.95),
        user_id=state.get("user_id"),
    )
    return state


def save_expense(state: ExpenseGraphState, db: Session) -> ExpenseGraphState:
    txn = _get_txn(db, state["db_transaction_id"])
    expense = ExpenseService(db).save_from_transaction(
        txn,
        category=state.get("category") or "Other",
        subcategory=state.get("subcategory"),
        description=state.get("description"),
        confidence=float(state.get("confidence") or 0.0),
        source="auto" if not state.get("user_response") else "chat",
        direction=state.get("direction") or getattr(txn, "direction", None) or "debit",
    )
    if txn.clarification:
        txn.clarification.status = "confirmed"
    message = NotificationAgent().saved_message(
        amount=float(txn.amount),
        category=expense.category,
        subcategory=expense.subcategory,
        merchant=expense.merchant,
    )
    if not state.get("user_response"):
        who = f" · {txn.merchant}" if txn.merchant else ""
        try:
            from app.services.push_service import PushService

            PushService(db).notify_payment(
                title="Ledgerly",
                body=f"Tracked ₹{float(txn.amount):,.2f}{who} as {expense.category}",
                user_id=state.get("user_id") or txn.user_id,
            )
        except Exception as extra:  # noqa: BLE001
            logger.warning("Push after save_expense failed: %s", extra)
    return {
        **state,
        "expense_id": expense.id,
        "message": message,
        "needs_user": False,
    }


def update_dashboard(state: ExpenseGraphState, db: Session) -> ExpenseGraphState:
    summary = AnalyticsService(db).current_month_summary(user_id=state.get("user_id"))
    return {**state, "dashboard_summary": summary}


def route_after_ask(state: ExpenseGraphState) -> Literal["process_user_response", "__end__"]:
    if state.get("user_response"):
        return "process_user_response"
    return "__end__"
