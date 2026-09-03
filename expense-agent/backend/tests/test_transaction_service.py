from datetime import datetime, timedelta, timezone

from app.schemas.transaction_schema import PaymentEventIn
from app.services.transaction_service import TransactionService


def test_upi_and_sms_correlate_to_one_transaction(db):
    svc = TransactionService(db)
    ts = datetime(2026, 8, 11, 15, 30, tzinfo=timezone.utc)

    first = svc.ingest(
        PaymentEventIn(
            source="upi_notification",
            amount=450,
            merchant="PVR Cinemas",
            transaction_id="123456789",
            timestamp=ts,
            raw_text="₹450 paid to PVR Cinemas via UPI",
        )
    )
    second = svc.ingest(
        PaymentEventIn(
            source="bank_sms",
            amount=450,
            merchant="PVR Cinemas",
            upi_ref="123456789",
            timestamp=ts,
            raw_text="INR 450.00 debited from A/c XX1234 UPI Ref: 123456789 To: PVR Cinemas",
        )
    )

    assert first.transaction.id == second.transaction.id
    assert second.merged is True
    assert set(second.transaction.sources) == {"upi_notification", "bank_sms"}
    db.commit()

    from app.models import Expense, Transaction

    assert db.query(Transaction).count() == 1
    # High-confidence PVR should auto-save exactly one expense
    assert db.query(Expense).count() == 1


def test_different_upi_refs_are_not_merged(db):
    """Two ₹1 UPI payments to the same person/account stay as two rows."""
    svc = TransactionService(db)
    ts = datetime(2026, 8, 13, 6, 56, 28, tzinfo=timezone.utc)

    first = svc.ingest(
        PaymentEventIn(
            source="email",
            amount=1.0,
            merchant="KORIMI BHARGAVI",
            upi_ref="092208066993",
            transaction_id="092208066993",
            account_suffix="5628",
            timestamp=ts,
            raw_text="Rs.1.00 is debited towards VPA bhargavisweety62-1@okaxis (KORIMI BHARGAVI) UPI Ref 092208066993",
            payload={"direction": "debit"},
        ),
        run_graph=False,
    )
    second = svc.ingest(
        PaymentEventIn(
            source="email",
            amount=1.0,
            merchant="KORIMI BHARGAVI",
            upi_ref="895407905915",
            transaction_id="895407905915",
            account_suffix="5628",
            timestamp=ts + timedelta(minutes=2),
            raw_text="Rs.1.00 is debited towards VPA bhargavisweety62-1@okaxis (KORIMI BHARGAVI) UPI Ref 895407905915",
            payload={"direction": "debit"},
        ),
        run_graph=False,
    )

    assert first.created_new is True
    assert second.created_new is True
    assert second.merged is False
    assert first.transaction.id != second.transaction.id
    db.commit()

    from app.models import Transaction

    assert db.query(Transaction).count() == 2
