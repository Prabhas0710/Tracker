from datetime import datetime, timezone

from app.models import ClarificationRequest, Expense, MerchantMemory
from app.schemas.transaction_schema import PaymentEventIn
from app.services.transaction_service import TransactionService


def test_pvr_auto_classifies_without_asking(db):
    svc = TransactionService(db)
    result = svc.ingest(
        PaymentEventIn(
            source="upi_notification",
            amount=450,
            merchant="PVR Cinemas",
            transaction_id="TXN-PVR-1",
            timestamp=datetime.now(timezone.utc),
            raw_text="₹450 paid to PVR Cinemas via UPI",
        )
    )
    db.commit()

    assert result.transaction.status == "saved"
    assert result.classification
    assert result.classification["category"] == "Entertainment"
    assert float(result.classification["confidence"]) >= 0.9
    assert result.transaction.expense_id is not None
    assert db.query(ClarificationRequest).count() == 0
    assert db.query(Expense).count() == 1


def test_swiggy_auto_classifies(db):
    svc = TransactionService(db)
    result = svc.ingest(
        PaymentEventIn(
            source="upi_notification",
            amount=380,
            merchant="Swiggy",
            timestamp=datetime.now(timezone.utc),
            raw_text="₹380 paid to Swiggy",
        )
    )
    db.commit()
    assert result.classification["category"] == "Food"
    assert result.transaction.status == "saved"
