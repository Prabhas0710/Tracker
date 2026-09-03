from datetime import datetime, timezone

from app.models import ClarificationRequest, Expense, MerchantMemory
from app.schemas.expense_schema import ExpenseUpdate
from app.schemas.transaction_schema import PaymentEventIn
from app.services.expense_service import ExpenseService
from app.services.transaction_service import TransactionService


AIRTEL_MAIL = (
    "Rs.349.00 is debited from your account ending 5628 towards "
    "VPA airtel-prepaid.paytm@ptybl (Airtel) on 12-08-26."
)


def test_unknown_merchant_saves_as_personal(db):
    svc = TransactionService(db)
    first = svc.ingest(
        PaymentEventIn(
            source="upi_notification",
            amount=1800,
            merchant="ABC Services",
            transaction_id="ABC-1",
            timestamp=datetime.now(timezone.utc),
            raw_text="₹1800 paid to ABC Services via UPI",
        )
    )
    db.commit()

    assert first.transaction.status == "saved"
    assert first.classification["category"] == "Personal"
    assert db.query(ClarificationRequest).count() == 0
    expense = db.query(Expense).one()
    assert expense.category == "Personal"

    ExpenseService(db).update(expense.id, ExpenseUpdate(category="Transport", subcategory="Vehicle Maintenance"))
    db.commit()

    second = svc.ingest(
        PaymentEventIn(
            source="upi_notification",
            amount=900,
            merchant="ABC Services",
            transaction_id="ABC-2",
            timestamp=datetime.now(timezone.utc),
            raw_text="₹900 paid to ABC Services via UPI",
        )
    )
    db.commit()
    assert second.transaction.status == "saved"
    assert second.classification["category"] == "Transport"
    assert second.classification["source"] == "memory"


def test_person_payee_uses_memory_when_user_taught_it(db):
    db.add(
        MerchantMemory(
            user_id=1,
            merchant_key="korimi bhargavi",
            merchant_display="KORIMI BHARGAVI",
            category="See You Next Time",
            subcategory=None,
            confidence=0.99,
            hit_count=3,
        )
    )
    db.commit()
    svc = TransactionService(db)
    result = svc.ingest(
        PaymentEventIn(
            source="email",
            amount=1.0,
            merchant="KORIMI BHARGAVI",
            upi_ref="982718378081",
            transaction_id="982718378081",
            timestamp=datetime.now(timezone.utc),
            raw_text="Rs.1.00 is debited towards VPA bhargavisweety62-1@okaxis (KORIMI BHARGAVI)",
            payload={"direction": "debit"},
        )
    )
    db.commit()
    assert result.transaction.status == "saved"
    assert db.query(ClarificationRequest).count() == 0
    expense = db.query(Expense).one()
    assert expense.category == "See You Next Time"


def test_person_payee_without_memory_is_personal(db):
    svc = TransactionService(db)
    result = svc.ingest(
        PaymentEventIn(
            source="email",
            amount=1.0,
            merchant="KORIMI BHARGAVI",
            upi_ref="111222333444",
            transaction_id="111222333444",
            timestamp=datetime.now(timezone.utc),
            raw_text="Rs.1.00 is debited towards VPA bhargavisweety62-1@okaxis (KORIMI BHARGAVI)",
            payload={"direction": "debit"},
        )
    )
    db.commit()
    assert result.transaction.status == "saved"
    assert result.classification["category"] == "Personal"
    assert db.query(ClarificationRequest).count() == 0


def test_airtel_prepaid_mail_is_recharge(db):
    svc = TransactionService(db)
    result = svc.ingest(
        PaymentEventIn(
            source="email",
            amount=349.0,
            merchant="Airtel",
            upi_ref="349prepaid1",
            transaction_id="349prepaid1",
            timestamp=datetime.now(timezone.utc),
            raw_text=AIRTEL_MAIL,
            payload={"direction": "debit"},
        )
    )
    db.commit()
    assert result.transaction.status == "saved"
    assert result.classification["category"] == "Recharge"
    expense = db.query(Expense).one()
    assert expense.category == "Recharge"
    assert db.query(ClarificationRequest).count() == 0
