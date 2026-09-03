"""Remove duplicate expenses created from repeated bank emails."""

from __future__ import annotations

from collections import defaultdict
from typing import Any, Optional

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.logging import get_logger
from app.models import ChatMessage, Expense, GmailSyncedMessage, PaymentEvent, Transaction
from app.services.bank_email_parser import is_junk_merchant, is_real_reference_id

logger = get_logger(__name__)


class DeduplicateService:
    def __init__(self, db: Session):
        self.db = db
        self.settings = get_settings()

    def _real_ref(self, expense: Expense) -> Optional[str]:
        txn = expense.transaction
        if not txn:
            return None
        for value in (txn.upi_ref, txn.external_transaction_id):
            if not is_real_reference_id(value):
                continue
            ref = str(value).strip()
            if ref.lower().startswith("upi:"):
                ref = ref.split(":", 1)[1].strip()
            if ref:
                return ref
        return None

    def _group_key(self, expense: Expense) -> tuple:
        spent = expense.spent_at
        # Bucket to the minute so near-identical alerts collapse together
        minute = spent.replace(second=0, microsecond=0) if spent else None
        ref = self._real_ref(expense)
        # Distinct UPI refs are distinct payments even at the same amount/minute
        return (
            expense.user_id,
            float(expense.amount),
            expense.direction or "debit",
            ref or minute,
        )

    def _score(self, expense: Expense) -> tuple:
        txn = expense.transaction
        has_upi = (
            1
            if txn
            and (
                txn.upi_ref
                or (
                    txn.external_transaction_id
                    and ":" not in str(txn.external_transaction_id)
                )
            )
            else 0
        )
        good_merchant = 1 if expense.merchant and not is_junk_merchant(expense.merchant) else 0
        return (has_upi, good_merchant, -expense.id)

    def cleanup(self, user_id: Optional[int] = None) -> dict[str, Any]:
        user_id = user_id or self.settings.default_user_id
        expenses = (
            self.db.query(Expense)
            .filter(Expense.user_id == user_id)
            .order_by(Expense.id.asc())
            .all()
        )
        groups: dict[tuple, list[Expense]] = defaultdict(list)
        for expense in expenses:
            groups[self._group_key(expense)].append(expense)

        removed_expenses = 0
        kept = 0

        for _key, rows in groups.items():
            if len(rows) < 2:
                kept += len(rows)
                continue
            ranked = sorted(rows, key=self._score, reverse=True)
            winner = ranked[0]
            kept += 1
            for dup in ranked[1:]:
                self._absorb_and_delete(winner, dup)
                removed_expenses += 1

        self.db.commit()
        return {
            "kept": kept,
            "removed_expenses": removed_expenses,
            "message": (
                f"Deduped expenses: kept {kept}, removed {removed_expenses} duplicates."
            ),
        }

    def _absorb_and_delete(self, winner: Expense, dup: Expense) -> None:
        winner_txn = winner.transaction
        dup_txn = dup.transaction

        if winner_txn and dup_txn:
            if (not winner_txn.merchant or is_junk_merchant(winner_txn.merchant)) and dup_txn.merchant:
                if not is_junk_merchant(dup_txn.merchant):
                    winner_txn.merchant = dup_txn.merchant
                    winner.merchant = dup_txn.merchant
            if not winner_txn.upi_ref and dup_txn.upi_ref:
                winner_txn.upi_ref = dup_txn.upi_ref
            if not winner_txn.external_transaction_id and dup_txn.external_transaction_id:
                winner_txn.external_transaction_id = dup_txn.external_transaction_id
            if not winner_txn.account_suffix and dup_txn.account_suffix:
                winner_txn.account_suffix = dup_txn.account_suffix

            sources = list(winner_txn.sources or [])
            for src in dup_txn.sources or []:
                if src not in sources:
                    sources.append(src)
            winner_txn.sources = sources

            raws = list(winner_txn.raw_texts or [])
            for raw in dup_txn.raw_texts or []:
                if raw not in raws:
                    raws.append(raw)
            winner_txn.raw_texts = raws

            self.db.query(PaymentEvent).filter(
                PaymentEvent.correlated_transaction_id == dup_txn.id
            ).update({"correlated_transaction_id": winner_txn.id}, synchronize_session=False)

            self.db.query(GmailSyncedMessage).filter(
                GmailSyncedMessage.transaction_id == dup_txn.id
            ).update({"transaction_id": winner_txn.id}, synchronize_session=False)

            clar = dup_txn.clarification
            if clar:
                self.db.query(ChatMessage).filter(
                    ChatMessage.clarification_id == clar.id
                ).update({"clarification_id": None}, synchronize_session=False)
                self.db.delete(clar)

        self.db.query(ChatMessage).filter(ChatMessage.expense_id == dup.id).update(
            {"expense_id": winner.id}, synchronize_session=False
        )

        dup_id = dup.id
        dup_txn_id = dup.transaction_id
        self.db.delete(dup)
        self.db.flush()
        if dup_txn_id and (not winner_txn or dup_txn_id != winner_txn.id):
            orphan = self.db.get(Transaction, dup_txn_id)
            if orphan:
                self.db.delete(orphan)
        logger.info("Removed duplicate expense %s (kept %s)", dup_id, winner.id)
