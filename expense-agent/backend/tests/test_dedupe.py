from datetime import datetime, timezone

from app.schemas.transaction_schema import PaymentEventIn
from app.services.transaction_service import TransactionService


def test_duplicate_email_events_merge(db):
    ts = datetime(2026, 8, 6, 14, 10, 3, tzinfo=timezone.utc)
    fingerprint = "cc_bill_payment:debit:12771.91:1007:06-aug-2026"
    first = PaymentEventIn(
        source="email",
        amount=12771.91,
        merchant="ICICI Credit Card Bill Payment",
        transaction_id=fingerprint,
        account_suffix="1007",
        timestamp=ts,
        raw_text="payment received INR 12771.91 card 1007",
        payload={"direction": "debit", "fingerprint": fingerprint},
    )
    second = PaymentEventIn(
        source="email",
        amount=12771.91,
        merchant="junk sole discretion of ICICI Bank",
        transaction_id=fingerprint,
        account_suffix="1007",
        timestamp=ts,
        raw_text="payment received INR 12771.91 card 1007 again",
        payload={"direction": "debit", "fingerprint": fingerprint},
    )
    svc = TransactionService(db)
    a = svc.ingest(first, run_graph=False)
    b = svc.ingest(second, run_graph=False)
    db.commit()
    assert a.created_new is True
    assert b.merged is True
    assert a.transaction.id == b.transaction.id


def test_cleanup_keeps_same_minute_payments_with_different_upi_refs(db):
    from datetime import timedelta, timezone

    from app.models import Expense, Transaction
    from app.services.deduplicate_service import DeduplicateService

    ts = datetime(2026, 8, 13, 6, 56, tzinfo=timezone.utc)
    user_id = 1
    first = Transaction(
        user_id=user_id,
        amount=1.0,
        merchant="KORIMI BHARGAVI",
        payment_method="UPI",
        external_transaction_id="092208066993",
        upi_ref="092208066993",
        sources=["email"],
        status="saved",
        direction="debit",
        event_timestamp=ts,
        raw_texts=["first"],
        account_suffix="5628",
    )
    second = Transaction(
        user_id=user_id,
        amount=1.0,
        merchant="KORIMI BHARGAVI",
        payment_method="UPI",
        external_transaction_id="895407905915",
        upi_ref="895407905915",
        sources=["email"],
        status="saved",
        direction="debit",
        event_timestamp=ts + timedelta(seconds=40),
        raw_texts=["second"],
        account_suffix="5628",
    )
    db.add_all([first, second])
    db.flush()
    db.add_all(
        [
            Expense(
                user_id=user_id,
                transaction_id=first.id,
                amount=1.0,
                merchant="KORIMI BHARGAVI",
                category="Personal",
                source="auto",
                direction="debit",
                spent_at=ts,
            ),
            Expense(
                user_id=user_id,
                transaction_id=second.id,
                amount=1.0,
                merchant="KORIMI BHARGAVI",
                category="Personal",
                source="auto",
                direction="debit",
                spent_at=ts + timedelta(seconds=40),
            ),
        ]
    )
    db.commit()

    result = DeduplicateService(db).cleanup(user_id=user_id)
    assert result["removed_expenses"] == 0
    assert db.query(Expense).count() == 2
    assert db.query(Transaction).count() == 2
