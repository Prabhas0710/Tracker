"""Per-bank credit card billing cycles (ICICI / HDFC)."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Literal, Optional
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import UserPreference
from app.models.transaction import Transaction
from app.services.bank_email_parser import detect_credit_card_issuer

IST = ZoneInfo("Asia/Kolkata")

CardBank = Literal["ICICI", "HDFC"]
SUPPORTED_BANKS: tuple[CardBank, ...] = ("ICICI", "HDFC")

# Legacy single-cycle keys (migrated to ICICI)
LEGACY_START_KEY = "cc_bill_cycle_start_at"
LEGACY_PAID_AT_KEY = "cc_bill_cycle_paid_at"
LEGACY_AMOUNT_KEY = "cc_bill_cycle_amount"
LEGACY_CARD_KEY = "cc_bill_cycle_card_suffix"


def _bank_key(bank: CardBank, field: str) -> str:
    return f"cc_cycle_{bank.lower()}_{field}"


def cycle_start_after_payment(paid_at: datetime) -> datetime:
    """Spends on/after the day after bill payment belong to the new cycle."""
    local = paid_at.astimezone(IST)
    next_day = local.date() + timedelta(days=1)
    return datetime(next_day.year, next_day.month, next_day.day, tzinfo=IST)


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
) -> Literal["current", "due"]:
    """Whether a CC spend counts in the current cycle or prior bill (due) for a month view."""
    local = spent_at.astimezone(IST)
    if cycle_start is None:
        # No bill-payment email for this bank yet — all spends are current cycle
        return "current"
    cs = cycle_start.astimezone(IST)
    if cs > month_end:
        return "due"
    if cs <= month_start:
        return "current"
    return "current" if local >= cs else "due"


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
        return {
            "bank": bank,
            "cycle_start_at": start.isoformat() if start else None,
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

    def record_bill_payment(
        self,
        *,
        bank: CardBank,
        user_id: Optional[int] = None,
        paid_at: datetime,
        amount: float,
        account_suffix: Optional[str] = None,
    ) -> Optional[datetime]:
        """Advance the CC cycle for one bank when a bill-payment ack email arrives."""
        user_id = user_id or self.settings.default_user_id
        if paid_at.tzinfo is None:
            paid_at = paid_at.replace(tzinfo=IST)
        else:
            paid_at = paid_at.astimezone(IST)

        cycle_start = cycle_start_after_payment(paid_at)
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
