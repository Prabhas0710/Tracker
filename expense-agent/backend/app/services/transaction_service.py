"""Transaction ingestion, correlation, and classification orchestration."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from difflib import SequenceMatcher
from typing import Any, Optional

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.logging import get_logger
from app.models import PaymentEvent, Transaction
from app.schemas.transaction_schema import (
    IngestResult,
    PaymentEventIn,
    TransactionOut,
)
from app.services.bank_email_parser import is_junk_merchant, is_real_reference_id
from app.services.payment_parser import normalize_merchant_key, parse_payment_text

logger = get_logger(__name__)


def _merchant_similarity(a: Optional[str], b: Optional[str]) -> float:
    if not a or not b:
        return 0.0
    if is_junk_merchant(a) or is_junk_merchant(b):
        return 0.0
    ka = normalize_merchant_key(a) or ""
    kb = normalize_merchant_key(b) or ""
    if not ka or not kb:
        return 0.0
    if ka == kb or ka in kb or kb in ka:
        return 1.0
    return SequenceMatcher(None, ka, kb).ratio()


def _prefer_merchant(current: Optional[str], incoming: Optional[str]) -> Optional[str]:
    if incoming and not is_junk_merchant(incoming):
        if not current or is_junk_merchant(current):
            return incoming
    return current or incoming


def _canonical_real_ref(value: Optional[str]) -> Optional[str]:
    """Normalize a bank/UPI id so 'upi:123' and '123' compare as the same payment."""
    if not is_real_reference_id(value):
        return None
    ref = str(value).strip()
    if ref.lower().startswith("upi:"):
        ref = ref.split(":", 1)[1].strip()
    return ref or None


def _incoming_real_refs(normalized: dict[str, Any]) -> set[str]:
    refs: set[str] = set()
    for value in (
        normalized.get("upi_ref"),
        normalized.get("transaction_id"),
        normalized.get("fingerprint"),
    ):
        canonical = _canonical_real_ref(value)
        if canonical:
            refs.add(canonical)
    return refs


def _txn_real_refs(txn: Transaction) -> set[str]:
    refs: set[str] = set()
    for value in (txn.upi_ref, txn.external_transaction_id):
        canonical = _canonical_real_ref(value)
        if canonical:
            refs.add(canonical)
    return refs


def _distinct_real_payments(normalized: dict[str, Any], txn: Transaction) -> bool:
    """True when both sides have real UPI/bank refs and none overlap — two payments."""
    incoming = _incoming_real_refs(normalized)
    existing = _txn_real_refs(txn)
    if not incoming or not existing:
        return False
    return incoming.isdisjoint(existing)


class TransactionService:
    def __init__(self, db: Session):
        self.db = db
        self.settings = get_settings()

    def normalize_event(self, event: PaymentEventIn) -> dict[str, Any]:
        normalized = parse_payment_text(
            event.raw_text,
            amount=event.amount,
            merchant=event.merchant,
            transaction_id=event.transaction_id,
            upi_ref=event.upi_ref,
            account_suffix=event.account_suffix,
            payment_method=event.payment_method,
            timestamp=event.timestamp,
            source=event.source,
        )
        payload = event.payload or {}
        direction = payload.get("direction") or "debit"
        if direction not in {"debit", "credit"}:
            direction = "debit"
        normalized["direction"] = direction
        normalized["hint_category"] = payload.get("category")
        normalized["hint_subcategory"] = payload.get("subcategory")
        normalized["hint_description"] = payload.get("description")
        normalized["hint_confidence"] = payload.get("confidence")
        if payload.get("fingerprint"):
            normalized["fingerprint"] = payload["fingerprint"]
        if is_junk_merchant(normalized.get("merchant")):
            normalized["merchant"] = None
        if not normalized.get("transaction_id") and payload.get("fingerprint"):
            normalized["transaction_id"] = payload["fingerprint"]
        return normalized

    def find_matching_transaction(self, normalized: dict[str, Any], user_id: int) -> Optional[Transaction]:
        refs = [
            r
            for r in [
                normalized.get("upi_ref"),
                normalized.get("transaction_id"),
                normalized.get("fingerprint"),
            ]
            if r
        ]
        if refs:
            for ref in refs:
                match = (
                    self.db.query(Transaction)
                    .filter(
                        Transaction.user_id == user_id,
                        (Transaction.upi_ref == ref) | (Transaction.external_transaction_id == ref),
                    )
                    .order_by(Transaction.id.desc())
                    .first()
                )
                if match and not _distinct_real_payments(normalized, match):
                    return match

        amount = float(normalized["amount"])
        ts: datetime = normalized["timestamp"]
        direction = normalized.get("direction") or "debit"
        window = timedelta(minutes=self.settings.correlation_window_minutes)
        candidates = (
            self.db.query(Transaction)
            .filter(
                Transaction.user_id == user_id,
                Transaction.amount == amount,
                Transaction.event_timestamp >= ts - window,
                Transaction.event_timestamp <= ts + window,
            )
            .order_by(Transaction.id.desc())
            .all()
        )
        best: Optional[Transaction] = None
        best_score = 0.0
        for txn in candidates:
            txn_direction = getattr(txn, "direction", None) or "debit"
            if txn_direction != direction:
                continue
            # Two UPI payments can share amount, account, and payee within minutes.
            if _distinct_real_payments(normalized, txn):
                continue

            # Same card/account + same amount in window = same payment
            if normalized.get("account_suffix") and txn.account_suffix:
                if normalized["account_suffix"] == txn.account_suffix:
                    return txn

            delta = abs((txn.event_timestamp - ts).total_seconds())
            # Duplicate bank emails often share the exact same Date header
            if (
                delta <= 90
                and normalized.get("source") == "email"
                and "email" in (txn.sources or [])
            ):
                return txn

            score = _merchant_similarity(txn.merchant, normalized.get("merchant"))
            if normalized.get("account_suffix") and txn.account_suffix:
                if normalized["account_suffix"] == txn.account_suffix:
                    score += 0.15
            if (
                is_junk_merchant(txn.merchant)
                and is_junk_merchant(normalized.get("merchant"))
                and delta <= 300
            ):
                score = max(score, 0.8)
            if score >= 0.72 and score > best_score:
                best = txn
                best_score = score
            elif not txn.merchant and not normalized.get("merchant") and delta <= 300:
                if best is None or best_score < 0.7:
                    best = txn
                    best_score = 0.7
        return best

    def merge_into_transaction(
        self, txn: Transaction, normalized: dict[str, Any], source: str
    ) -> Transaction:
        sources = list(txn.sources or [])
        if source not in sources:
            sources.append(source)
        txn.sources = sources

        raw_texts = list(txn.raw_texts or [])
        if normalized["raw_text"] not in raw_texts:
            raw_texts.append(normalized["raw_text"])
        txn.raw_texts = raw_texts

        preferred = _prefer_merchant(txn.merchant, normalized.get("merchant"))
        if preferred:
            txn.merchant = preferred
            if txn.expense and (not txn.expense.merchant or is_junk_merchant(txn.expense.merchant)):
                txn.expense.merchant = preferred

        if normalized.get("upi_ref"):
            txn.upi_ref = txn.upi_ref or normalized["upi_ref"]

        incoming_id = normalized.get("upi_ref") or normalized.get("transaction_id") or normalized.get(
            "fingerprint"
        )
        if incoming_id:
            if not txn.external_transaction_id:
                txn.external_transaction_id = incoming_id
            elif normalized.get("upi_ref") and not str(txn.external_transaction_id).startswith("upi:"):
                # Upgrade synthetic fingerprint to real UPI ref when available
                if ":" in str(txn.external_transaction_id) or not txn.upi_ref:
                    txn.external_transaction_id = normalized["upi_ref"]
                    txn.upi_ref = normalized["upi_ref"]

        if not txn.account_suffix and normalized.get("account_suffix"):
            txn.account_suffix = normalized["account_suffix"]
        if not txn.payment_method and normalized.get("payment_method"):
            txn.payment_method = normalized["payment_method"]
        if normalized.get("direction"):
            txn.direction = normalized["direction"]
        return txn

    def create_transaction(self, normalized: dict[str, Any], user_id: int) -> Transaction:
        external_id = (
            normalized.get("upi_ref")
            or normalized.get("transaction_id")
            or normalized.get("fingerprint")
        )
        return Transaction(
            user_id=user_id,
            amount=normalized["amount"],
            merchant=normalized.get("merchant"),
            payment_method=normalized.get("payment_method"),
            external_transaction_id=external_id,
            upi_ref=normalized.get("upi_ref"),
            sources=[normalized["source"]],
            status="pending",
            direction=normalized.get("direction") or "debit",
            event_timestamp=normalized["timestamp"],
            raw_texts=[normalized["raw_text"]],
            account_suffix=normalized.get("account_suffix"),
        )

    def ingest(
        self,
        event: PaymentEventIn,
        user_id: Optional[int] = None,
        *,
        run_graph: bool = True,
    ) -> IngestResult:
        user_id = user_id or self.settings.default_user_id
        normalized = self.normalize_event(event)
        existing = self.find_matching_transaction(normalized, user_id)
        created_new = existing is None
        merged = False

        if existing:
            txn = self.merge_into_transaction(existing, normalized, normalized["source"])
            merged = True
        else:
            txn = self.create_transaction(normalized, user_id)
            self.db.add(txn)
            self.db.flush()

        payment_event = PaymentEvent(
            user_id=user_id,
            source=normalized["source"],
            amount=normalized["amount"],
            merchant=normalized.get("merchant"),
            payment_method=normalized.get("payment_method"),
            transaction_id=normalized.get("transaction_id"),
            upi_ref=normalized.get("upi_ref"),
            account_suffix=normalized.get("account_suffix"),
            raw_text=normalized["raw_text"],
            event_timestamp=normalized["timestamp"],
            payload_json=event.payload,
            correlated_transaction_id=txn.id,
        )
        self.db.add(payment_event)
        self.db.flush()

        classification: Optional[dict[str, Any]] = None
        if run_graph and txn.status != "saved" and txn.expense is None:
            from app.agents.expense_agent import ExpenseAgent  # lazy import

            agent = ExpenseAgent(self.db)
            classification = agent.process_transaction(txn.id)

        self.db.refresh(txn)
        return IngestResult(
            transaction=self.to_transaction_out(txn, classification),
            created_new=created_new,
            merged=merged,
            classification=classification,
        )

    def ingest_pair(
        self, upi: PaymentEventIn, sms: PaymentEventIn, user_id: Optional[int] = None
    ) -> IngestResult:
        if not sms.transaction_id and not sms.upi_ref:
            sms.transaction_id = upi.transaction_id or upi.upi_ref
            sms.upi_ref = upi.upi_ref or upi.transaction_id
        if not upi.transaction_id and not upi.upi_ref:
            upi.transaction_id = sms.transaction_id or sms.upi_ref
            upi.upi_ref = sms.upi_ref or sms.transaction_id

        self.ingest(upi, user_id=user_id, run_graph=False)
        second = self.ingest(sms, user_id=user_id, run_graph=True)
        return second

    def list_transactions(self, user_id: Optional[int] = None, limit: int = 50) -> list[TransactionOut]:
        user_id = user_id or self.settings.default_user_id
        rows = (
            self.db.query(Transaction)
            .filter(Transaction.user_id == user_id)
            .order_by(Transaction.event_timestamp.desc())
            .limit(limit)
            .all()
        )
        return [self.to_transaction_out(r) for r in rows]

    def to_transaction_out(
        self, txn: Transaction, classification: Optional[dict[str, Any]] = None
    ) -> TransactionOut:
        expense_id = txn.expense.id if txn.expense else None
        clarification_id = txn.clarification.id if txn.clarification else None
        category = None
        subcategory = None
        confidence = None
        message = None
        if txn.expense:
            category = txn.expense.category
            subcategory = txn.expense.subcategory
            confidence = txn.expense.confidence
        if classification:
            category = category or classification.get("category")
            subcategory = subcategory or classification.get("subcategory")
            confidence = confidence if confidence is not None else classification.get("confidence")
            message = classification.get("message")
        if txn.clarification and txn.status == "needs_user":
            message = message or txn.clarification.prompt_message
        return TransactionOut(
            id=txn.id,
            amount=float(txn.amount),
            merchant=txn.merchant,
            payment_method=txn.payment_method,
            external_transaction_id=txn.external_transaction_id,
            upi_ref=txn.upi_ref,
            sources=list(txn.sources or []),
            status=txn.status,
            event_timestamp=txn.event_timestamp,
            raw_texts=list(txn.raw_texts or []),
            expense_id=expense_id,
            clarification_id=clarification_id,
            category=category,
            subcategory=subcategory,
            confidence=confidence,
            message=message,
        )
