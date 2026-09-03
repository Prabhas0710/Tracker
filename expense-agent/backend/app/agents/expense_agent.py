"""Main orchestrator for payment classification and NL expense entry."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy.orm import Session

from app.agents.analytics_agent import AnalyticsAgent
from app.agents.category_agent import CategoryAgent
from app.agents.notification_agent import NotificationAgent
from app.core.config import get_settings
from app.core.logging import get_logger
from app.graph.expense_graph import resume_after_user_response, run_classification
from app.models import ChatMessage, ClarificationRequest, Transaction
from app.schemas.chat_schema import ChatResponse
from app.schemas.expense_schema import ExpenseCreate
from app.services.expense_service import ExpenseService
from app.services.payment_parser import parse_payment_text

logger = get_logger(__name__)


class ExpenseAgent:
    def __init__(self, db: Session):
        self.db = db
        self.settings = get_settings()

    def process_transaction(self, transaction_id: int) -> dict[str, Any]:
        result = run_classification(self.db, transaction_id)
        self.db.flush()
        return {
            "category": result.get("category"),
            "subcategory": result.get("subcategory"),
            "description": result.get("description"),
            "confidence": result.get("confidence"),
            "needs_user": result.get("needs_user", False),
            "expense_id": result.get("expense_id"),
            "clarification_id": result.get("clarification_id"),
            "message": result.get("message"),
            "dashboard_summary": result.get("dashboard_summary"),
            "classification_source": result.get("classification_source"),
            "source": result.get("classification_source"),
        }

    def handle_clarification_response(
        self, clarification_id: int, message: str, user_id: Optional[int] = None
    ) -> ChatResponse:
        user_id = user_id or self.settings.default_user_id
        clarification = (
            self.db.query(ClarificationRequest)
            .filter(
                ClarificationRequest.id == clarification_id,
                ClarificationRequest.user_id == user_id,
            )
            .first()
        )
        if not clarification:
            return ChatResponse(reply="I couldn't find that clarification request.")

        result = resume_after_user_response(
            self.db,
            clarification.transaction_id,
            message,
            clarification_id=clarification.id,
        )
        self.db.add(
            ChatMessage(
                user_id=user_id,
                role="user",
                content=message,
                clarification_id=clarification.id,
                expense_id=result.get("expense_id"),
            )
        )
        reply = result.get("message") or "Expense saved."
        self.db.add(
            ChatMessage(
                user_id=user_id,
                role="assistant",
                content=reply,
                clarification_id=clarification.id,
                expense_id=result.get("expense_id"),
            )
        )
        self.db.commit()
        return ChatResponse(
            reply=reply,
            clarification_id=clarification.id,
            expense_id=result.get("expense_id"),
            needs_confirm=False,
            proposed={
                "category": result.get("category"),
                "subcategory": result.get("subcategory"),
                "description": result.get("description"),
            },
            dashboard_hint=result.get("dashboard_summary"),
        )

    def confirm_clarification(
        self,
        clarification_id: int,
        *,
        confirmed: bool = True,
        category: Optional[str] = None,
        subcategory: Optional[str] = None,
        description: Optional[str] = None,
        user_id: Optional[int] = None,
    ) -> ChatResponse:
        user_id = user_id or self.settings.default_user_id
        clarification = (
            self.db.query(ClarificationRequest)
            .filter(
                ClarificationRequest.id == clarification_id,
                ClarificationRequest.user_id == user_id,
            )
            .first()
        )
        if not clarification:
            return ChatResponse(reply="Clarification not found.")

        if not confirmed:
            clarification.status = "cancelled"
            self.db.commit()
            return ChatResponse(reply="Okay, I cancelled that clarification.", clarification_id=clarification_id)

        txn = self.db.get(Transaction, clarification.transaction_id)
        if not txn:
            return ChatResponse(reply="Transaction missing.")

        # Expense may already exist as Other from low-confidence auto-save
        if txn.expense and (category or subcategory is not None or description is not None):
            if category:
                txn.expense.category = category
            if subcategory is not None:
                txn.expense.subcategory = subcategory
            elif category:
                txn.expense.subcategory = None
            if description is not None:
                txn.expense.description = description
            txn.expense.confidence = 1.0
            txn.status = "saved"
            clarification.status = "confirmed"
            clarification.proposed_category = txn.expense.category
            clarification.proposed_subcategory = txn.expense.subcategory
            from app.agents.memory_agent import MemoryAgent

            MemoryAgent(self.db).learn(
                merchant=txn.merchant,
                category=txn.expense.category,
                subcategory=txn.expense.subcategory,
                confidence=1.0,
                user_id=user_id,
            )
            self.db.commit()
            msg = NotificationAgent().saved_message(
                amount=float(txn.amount),
                category=txn.expense.category,
                subcategory=txn.expense.subcategory,
                merchant=txn.merchant,
            )
            return ChatResponse(reply=msg, expense_id=txn.expense.id, clarification_id=clarification_id)

        if txn.expense and confirmed and not category:
            msg = NotificationAgent().saved_message(
                amount=float(txn.amount),
                category=txn.expense.category,
                subcategory=txn.expense.subcategory,
                merchant=txn.merchant,
            )
            return ChatResponse(
                reply=f"{msg}\n\nStill under Other — pick a category to replace it.",
                expense_id=txn.expense.id,
                clarification_id=clarification_id,
                needs_confirm=True,
            )

        text = description or clarification.user_response or clarification.proposed_description or "Expense"
        if category:
            clarification.proposed_category = category
        if subcategory:
            clarification.proposed_subcategory = subcategory
        if description:
            clarification.proposed_description = description

        result = resume_after_user_response(
            self.db,
            txn.id,
            clarification.user_response
            or f"{clarification.proposed_category or category}: {text}",
            clarification_id=clarification.id,
        )
        # Apply explicit overrides after save
        if txn.expense and (category or subcategory or description):
            if category:
                txn.expense.category = category
            if subcategory is not None:
                txn.expense.subcategory = subcategory
            if description is not None:
                txn.expense.description = description
        self.db.commit()
        return ChatResponse(
            reply=result.get("message") or "Expense saved.",
            expense_id=result.get("expense_id"),
            clarification_id=clarification_id,
            dashboard_hint=result.get("dashboard_summary"),
        )

    def handle_chat(
        self,
        message: str,
        clarification_id: Optional[int] = None,
        conversation_id: Optional[int] = None,
    ) -> ChatResponse:
        if clarification_id:
            return self.handle_clarification_response(clarification_id, message)
        from app.services.assistant_service import AssistantService

        return AssistantService(self.db).reply(message, conversation_id=conversation_id)

    def create_manual_from_nl(self, text: str) -> ChatResponse:
        user_id = self.settings.default_user_id
        amount = None
        try:
            parsed = parse_payment_text(text, source="manual")
            amount = parsed["amount"]
            merchant = parsed.get("merchant")
        except ValueError:
            merchant = None
            # Try loose amount extract
            match = re.search(
                r"(?:₹|INR|Rs\.?)?\s*([0-9]{1,3}(?:,[0-9]{2,3})*(?:\.[0-9]{1,2})?|[0-9]+(?:\.[0-9]{1,2})?)",
                text,
                re.I,
            )
            if match:
                amount = float(match.group(1).replace(",", ""))

        if amount is None:
            self.db.add(ChatMessage(user_id=user_id, role="user", content=text))
            reply = "I need an amount to save an expense. Try: Spent ₹500 on movie"
            self.db.add(ChatMessage(user_id=user_id, role="assistant", content=reply))
            self.db.commit()
            return ChatResponse(reply=reply)

        classified = CategoryAgent(self.db).parse_user_response(
            text, merchant=merchant, amount=amount
        )
        expense = ExpenseService(self.db).create(
            ExpenseCreate(
                amount=amount,
                category=classified.get("category") or "Other",
                subcategory=classified.get("subcategory"),
                description=classified.get("description") or text,
                merchant=merchant,
                spent_at=datetime.now(timezone.utc),
            ),
            user_id=user_id,
            source="chat",
        )
        if merchant:
            from app.agents.memory_agent import MemoryAgent

            MemoryAgent(self.db).learn(
                merchant=merchant,
                category=expense.category,
                subcategory=expense.subcategory,
                user_id=user_id,
            )
        reply = NotificationAgent().saved_message(
            amount=float(expense.amount),
            category=expense.category,
            subcategory=expense.subcategory,
            merchant=expense.merchant,
        )
        self.db.add(ChatMessage(user_id=user_id, role="user", content=text, expense_id=expense.id))
        self.db.add(
            ChatMessage(user_id=user_id, role="assistant", content=reply, expense_id=expense.id)
        )
        self.db.commit()
        return ChatResponse(reply=reply, expense_id=expense.id)

    def analytics_insight(self, year: int, month: int) -> dict[str, Any]:
        return AnalyticsAgent(self.db).monthly_insight(year, month)

    @staticmethod
    def _looks_like_new_expense(message: str) -> bool:
        return bool(re.search(r"(spent|paid|₹|inr|rs\.?)", message, re.I))
