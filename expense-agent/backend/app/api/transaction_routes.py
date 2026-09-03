from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.security import verify_mock_api_key
from app.database.database import get_db
from app.schemas.transaction_schema import (
    IngestResult,
    MockPaymentPairRequest,
    MockPaymentRequest,
    PaymentEventIn,
    TransactionOut,
)
from app.services.transaction_service import TransactionService

router = APIRouter(prefix="/api", tags=["payments"])


@router.post("/payments/events", response_model=IngestResult)
def ingest_payment_event(payload: PaymentEventIn, db: Session = Depends(get_db)):
    result = TransactionService(db).ingest(payload)
    db.commit()
    return result


@router.post("/payments/mock", response_model=IngestResult, dependencies=[Depends(verify_mock_api_key)])
def mock_payment(payload: MockPaymentRequest, db: Session = Depends(get_db)):
    event = PaymentEventIn(**payload.model_dump())
    result = TransactionService(db).ingest(event)
    db.commit()
    return result


@router.post(
    "/payments/mock/pair",
    response_model=IngestResult,
    dependencies=[Depends(verify_mock_api_key)],
)
def mock_payment_pair(payload: MockPaymentPairRequest, db: Session = Depends(get_db)):
    upi = PaymentEventIn(**payload.upi.model_dump())
    sms = PaymentEventIn(**payload.sms.model_dump())
    # Align refs for correlation when one side has the ID
    if upi.transaction_id or upi.upi_ref:
        sms.transaction_id = sms.transaction_id or upi.transaction_id or upi.upi_ref
        sms.upi_ref = sms.upi_ref or upi.upi_ref or upi.transaction_id
    if sms.transaction_id or sms.upi_ref:
        upi.transaction_id = upi.transaction_id or sms.transaction_id or sms.upi_ref
        upi.upi_ref = upi.upi_ref or sms.upi_ref or sms.transaction_id
    result = TransactionService(db).ingest_pair(upi, sms)
    db.commit()
    return result


@router.get("/transactions", response_model=list[TransactionOut])
def list_transactions(limit: int = 50, db: Session = Depends(get_db)):
    return TransactionService(db).list_transactions(limit=limit)


@router.post("/payments/dedupe")
def dedupe_payments(db: Session = Depends(get_db)):
    from app.services.deduplicate_service import DeduplicateService

    return DeduplicateService(db).cleanup()
