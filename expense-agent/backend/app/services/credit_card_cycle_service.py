"""Per-bank credit card billing cycles (ICICI / HDFC).

Statement cutoffs (IST):
- ICICI: statement day 6 → spends through 5th 23:59:59 are billed
- HDFC: statement day 1 → spends through previous month are billed

Marking a bill paid (Gmail ack or manual) sets cycle_start to that statement day.
Spends before cycle_start = paid/billed; spends on/after = unbilled current cycle.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal, Optional
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import Expense, UserPreference
from app.models.transaction import Transaction
from app.services.bank_email_parser import detect_credit_card_issuer

IST = ZoneInfo("Asia/Kolkata")

CardBank = Literal["ICICI", "HDFC"]
SUPPORTED_BANKS: tuple[CardBank, ...] = ("ICICI", "HDFC")

# Calendar day the statement opens / new cycle starts (IST midnight)
STATEMENT_DAY: dict[CardBank, int] = {
    "ICICI": 6,
    "HDFC": 1,
}

# Legacy single-cycle keys (migrated to ICICI)
LEGACY_START_KEY = "cc_bill_cycle_start_at"
LEGACY_PAID_AT_KEY = "cc_bill_cycle_paid_at"
LEGACY_AMOUNT_KEY = "cc_bill_cycle_amount"
LEGACY_CARD_KEY = "cc_bill_cycle_card_suffix"


def _bank_key(bank: CardBank, field: str) -> str:
    return f"cc_cycle_{bank.lower()}_{field}"


def _prev_month(year: int, month: int) -> tuple[int, int]:
    if month <= 1:
        return year - 1, 12
    return year, month - 1


def _next_month(year: int, month: int) -> tuple[int, int]:
    if month >= 12:
        return year + 1, 1
    return year, month + 1


def statement_datetime(bank: CardBank, year: int, month: int) -> datetime:
    day = STATEMENT_DAY[bank]
    return datetime(year, month, day, tzinfo=IST)


def cycle_start_for_bank_payment(bank: CardBank, paid_at: datetime) -> datetime:
    """New cycle starts at the statement date for the bill being paid."""
    local = paid_at.astimezone(IST) if paid_at.tzinfo else paid_at.replace(tzinfo=IST)
    day = STATEMENT_DAY[bank]
    if local.day >= day:
        return statement_datetime(bank, local.year, local.month)
    y, m = _prev_month(local.year, local.month)
    return statement_datetime(bank, y, m)


def cycle_start_after_payment(paid_at: datetime) -> datetime:
    """Legacy helper — prefers ICICI statement-day rules."""
    return cycle_start_for_bank_payment("ICICI", paid_at)


def next_statement_at(bank: CardBank, after: datetime) -> datetime:
    """Next statement instant strictly after `after` (exclusive end of open bill)."""
    local = after.astimezone(IST) if after.tzinfo else after.replace(tzinfo=IST)
    day = STATEMENT_DAY[bank]
    candidate = statement_datetime(bank, local.year, local.month)
    if candidate > local:
        return candidate
    y, m = _next_month(local.year, local.month)
    return statement_datetime(bank, y, m)


def normalize_card_bank(value: Optional[str]) -> Optional[CardBank]:
    if not value:
        return None
    upper = value.strip().upper()
    if upper in SUPPORTED_BANKS:
        return upper
    return None


def classify_cc_spend_in_month(
    spent_at: datetime,
    month_start: datetime,
    month_end: datetime,
    cycle_start: Optional[datetime],
    *,
    bank: Optional[CardBank] = None,
) -> Literal["current", "due", "bill"]:
    """Bucket a CC spend for a month view.

    - due: already paid (before last cycle_start)
    - bill: on the open statement (to pay next) — before next statement day
    - current: after the open statement day (unbilled next cycle)
    """
    local = spent_at.astimezone(IST)
    ms = month_start.astimezone(IST)

    if cycle_start is None:
        if not bank:
            return "bill"
        stmt = statement_datetime(bank, ms.year, ms.month)
        return "bill" if local < stmt else "current"

    cs = cycle_start.astimezone(IST)
    if cs > month_end.astimezone(IST):
        return "due"
    if local < cs:
        return "due"

    if not bank:
        return "bill"

    bill_end = next_statement_at(bank, cs)
    if local < bill_end:
        return "bill"
    return "current"


def infer_card_issuer_from_transaction(txn: Optional[Transaction]) -> Optional[CardBank]:
    if not txn:
        return None
    for raw in txn.raw_texts or []:
        found = detect_credit_card_issuer(str(raw))
        if found:
            return normalize_card_bank(found)
    return None


class CreditCardCycleService:
    def __init__(self, db: Session):
        self.db = db
        self.settings = get_settings()
        self._migrate_legacy_prefs()

    def get_cycle_start(self, bank: CardBank, user_id: Optional[int] = None) -> Optional[datetime]:
        raw = self._get_pref(user_id, _bank_key(bank, "start_at"))
        if not raw:
            return None
        try:
            return datetime.fromisoformat(raw)
        except ValueError:
            return None

    def get_bank_cycle_info(self, bank: CardBank, user_id: Optional[int] = None) -> dict[str, Any]:
        user_id = user_id or self.settings.default_user_id
        start = self.get_cycle_start(bank, user_id=user_id)
        paid_raw = self._get_pref(user_id, _bank_key(bank, "paid_at"))
        amount_raw = self._get_pref(user_id, _bank_key(bank, "amount"))
        card = self._get_pref(user_id, _bank_key(bank, "card_suffix"))
        paid_at = None
        if paid_raw:
            try:
                paid_at = datetime.fromisoformat(paid_raw)
            except ValueError:
                paid_at = None
        bill_closes_at = next_statement_at(bank, start) if start else None
        return {
            "bank": bank,
            "statement_day": STATEMENT_DAY[bank],
            "cycle_start_at": start.isoformat() if start else None,
            "bill_closes_at": bill_closes_at.isoformat() if bill_closes_at else None,
            "bill_paid_at": paid_at.isoformat() if paid_at else None,
            "bill_amount": float(amount_raw) if amount_raw else None,
            "card_suffix": card,
        }

    def get_all_cycles(self, user_id: Optional[int] = None) -> dict[str, Any]:
        banks = {bank: self.get_bank_cycle_info(bank, user_id=user_id) for bank in SUPPORTED_BANKS}
        # Backwards compatible single-cycle field (ICICI if set)
        icici = banks["ICICI"]
        return {
            "banks": banks,
            "cycle_start_at": icici.get("cycle_start_at"),
            "bill_paid_at": icici.get("bill_paid_at"),
            "bill_amount": icici.get("bill_amount"),
            "card_suffix": icici.get("card_suffix"),
        }

    def open_bill_amount(
        self,
        bank: CardBank,
        *,
        user_id: Optional[int] = None,
        paid_at: Optional[datetime] = None,
    ) -> float:
        """Sum of CC spends that will be marked paid for this bank."""
        user_id = user_id or self.settings.default_user_id
        paid_at = paid_at or datetime.now(IST)
        if paid_at.tzinfo is None:
            paid_at = paid_at.replace(tzinfo=IST)
        else:
            paid_at = paid_at.astimezone(IST)

        new_start = cycle_start_for_bank_payment(bank, paid_at)
        old_start = self.get_cycle_start(bank, user_id=user_id)

        q = (
            self.db.query(Expense, Transaction)
            .join(Transaction, Transaction.id == Expense.transaction_id)
            .filter(
                Expense.user_id == user_id,
                Expense.direction == "debit",
                Transaction.payment_method == "Credit Card",
                Expense.spent_at < new_start,
            )
        )
        if old_start is not None:
            q = q.filter(Expense.spent_at >= old_start)

        total = 0.0
        for expense, txn in q.all():
            if infer_card_issuer_from_transaction(txn) != bank:
                continue
            total += float(expense.amount)
        return round(total, 2)

    def record_bill_payment(
        self,
        *,
        bank: CardBank,
        user_id: Optional[int] = None,
        paid_at: datetime,
        amount: float,
        account_suffix: Optional[str] = None,
    ) -> Optional[datetime]:
        """Advance the CC cycle for one bank when a bill is paid (email or manual)."""
        user_id = user_id or self.settings.default_user_id
        if paid_at.tzinfo is None:
            paid_at = paid_at.replace(tzinfo=IST)
        else:
            paid_at = paid_at.astimezone(IST)

        cycle_start = cycle_start_for_bank_payment(bank, paid_at)
        existing_start = self.get_cycle_start(bank, user_id=user_id)
        existing_paid_raw = self._get_pref(user_id, _bank_key(bank, "paid_at"))
        existing_paid = None
        if existing_paid_raw:
            try:
                existing_paid = datetime.fromisoformat(existing_paid_raw)
            except ValueError:
                existing_paid = None

        if existing_paid and paid_at <= existing_paid:
            return existing_start

        self._set_pref(user_id, _bank_key(bank, "start_at"), cycle_start.isoformat())
        self._set_pref(user_id, _bank_key(bank, "paid_at"), paid_at.isoformat())
        self._set_pref(user_id, _bank_key(bank, "amount"), f"{float(amount):.2f}")
        if account_suffix:
            self._set_pref(user_id, _bank_key(bank, "card_suffix"), account_suffix)
        self.db.flush()
        return cycle_start

    def mark_bill_paid(
        self,
        bank: CardBank,
        *,
        user_id: Optional[int] = None,
        paid_at: Optional[datetime] = None,
        amount: Optional[float] = None,
    ) -> dict[str, Any]:
        """Manual mark-as-paid for a bank when Gmail did not auto-detect payment."""
        user_id = user_id or self.settings.default_user_id
        paid_at = paid_at or datetime.now(IST)
        if paid_at.tzinfo is None:
            paid_at = paid_at.replace(tzinfo=IST)
        else:
            paid_at = paid_at.astimezone(IST)

        if amount is None:
            amount = self.open_bill_amount(bank, user_id=user_id, paid_at=paid_at)

        cycle_start = self.record_bill_payment(
            bank=bank,
            user_id=user_id,
            paid_at=paid_at,
            amount=float(amount),
        )
        return {
            **self.get_bank_cycle_info(bank, user_id=user_id),
            "cycle_start_at": cycle_start.isoformat() if cycle_start else None,
            "marked_amount": float(amount),
        }

    def _migrate_legacy_prefs(self) -> None:
        user_id = self.settings.default_user_id
        legacy_start = self._get_pref(user_id, LEGACY_START_KEY)
        if not legacy_start:
            return
        if self._get_pref(user_id, _bank_key("ICICI", "start_at")):
            return
        for field, legacy_key in (
            ("start_at", LEGACY_START_KEY),
            ("paid_at", LEGACY_PAID_AT_KEY),
            ("amount", LEGACY_AMOUNT_KEY),
            ("card_suffix", LEGACY_CARD_KEY),
        ):
            val = self._get_pref(user_id, legacy_key)
            if val:
                self._set_pref(user_id, _bank_key("ICICI", field), val)

    def _get_pref(self, user_id: Optional[int], key: str) -> Optional[str]:
        user_id = user_id or self.settings.default_user_id
        row = (
            self.db.query(UserPreference)
            .filter(UserPreference.user_id == user_id, UserPreference.key == key)
            .order_by(UserPreference.id.desc())
            .first()
        )
        return row.value if row else None

    def _set_pref(self, user_id: int, key: str, value: str) -> None:
        row = (
            self.db.query(UserPreference)
            .filter(UserPreference.user_id == user_id, UserPreference.key == key)
            .first()
        )
        if row:
            row.value = value
        else:
            self.db.add(UserPreference(user_id=user_id, key=key, value=value))
