import time
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.agents.expense_agent import ExpenseAgent
from app.database.database import get_db
from app.schemas.expense_schema import ExpenseUpdate
from app.services.category_service import CategoryService
from app.services.expense_service import ExpenseService
from app.services.notification_service import NotificationService
from app.services.push_service import PushService
from app.services.voice_service import VoiceService

router = APIRouter(prefix="/api/voice", tags=["voice"])

_CLAIMS: dict[int, float] = {}
_CLAIM_SECONDS = 35.0


class SpeakIn(BaseModel):
    text: str = Field(..., min_length=1, max_length=4000)


class ResolveIn(BaseModel):
    clarification_id: int
    text: str = Field(..., min_length=1, max_length=500)


class PushSubscribeIn(BaseModel):
    endpoint: str = Field(..., min_length=8, max_length=2000)
    keys: dict[str, str]


@router.post("/speak")
def speak(payload: SpeakIn, db: Session = Depends(get_db)):
    try:
        audio = VoiceService(db).speak(payload.text)
    except Exception as extra:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"Voice failed: {extra}") from extra
    return Response(content=audio, media_type="audio/mpeg")


@router.post("/transcribe")
async def transcribe(file: UploadFile = File(...), db: Session = Depends(get_db)):
    data = await file.read()
    try:
        text = VoiceService(db).transcribe(
            data,
            filename=file.filename or "audio.webm",
            content_type=file.content_type or "audio/webm",
        )
    except Exception as extra:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"Listen failed: {extra}") from extra
    return {"text": text}


@router.post("/resolve")
def resolve(payload: ResolveIn, db: Session = Depends(get_db)):
    voice = VoiceService(db)
    category = voice.match_category(payload.text)
    if not category:
        return {"matched": False, "category": None, "reply": voice.retry_prompt(), "spoken": voice.retry_prompt()}

    if category == "Self Transfer":
        body_category, subcategory, direction = "Transfer", "Self", "transfer"
    elif category == "Other":
        body_category, subcategory, direction = "Other", "Unknown", "debit"
    elif category == "Income":
        body_category, subcategory, direction = "Income", None, "credit"
    else:
        body_category, subcategory, direction = category, None, "debit"

    CategoryService(db).ensure(body_category)
    result = ExpenseAgent(db).confirm_clarification(
        payload.clarification_id,
        confirmed=True,
        category=body_category,
        subcategory=subcategory,
        description=payload.text.strip(),
    )
    if result.expense_id and direction != "debit":
        ExpenseService(db).update(result.expense_id, ExpenseUpdate(direction=direction))
        db.commit()
    return {
        "matched": True,
        "category": category,
        "reply": result.reply,
        "spoken": voice.saved_prompt(category),
    }


@router.post("/claim/{clarification_id}")
def claim_clarification(clarification_id: int, db: Session = Depends(get_db)):
    """Only one open device should speak/listen for the same payment."""
    pending = next(
        (item for item in NotificationService(db).list_pending() if item.id == clarification_id),
        None,
    )
    if not pending:
        return {"claimed": False, "reason": "not_pending"}
    now = time.time()
    held = _CLAIMS.get(clarification_id, 0)
    if held and now - held < _CLAIM_SECONDS:
        return {"claimed": False, "reason": "busy"}
    _CLAIMS[clarification_id] = now
    return {"claimed": True}


@router.get("/pending-script/{clarification_id}")
def pending_script(clarification_id: int, db: Session = Depends(get_db)):
    pending = next(
        (item for item in NotificationService(db).list_pending() if item.id == clarification_id),
        None,
    )
    if not pending:
        raise HTTPException(status_code=404, detail="Not found")
    return {
        "text": VoiceService(db).question_for(
            amount=float(pending.amount or 0),
            merchant=pending.merchant,
        )
    }


@router.get("/push-key")
def push_key(db: Session = Depends(get_db)):
    key = PushService(db).public_key()
    if not key:
        raise HTTPException(status_code=503, detail="Push is not configured")
    return {"publicKey": key}


@router.post("/push-subscribe")
def push_subscribe(payload: PushSubscribeIn, db: Session = Depends(get_db)):
    p256dh = (payload.keys.get("p256dh") or "").strip()
    auth = (payload.keys.get("auth") or "").strip()
    if not p256dh or not auth:
        raise HTTPException(status_code=400, detail="Missing push keys")
    from app.core.config import get_settings

    row = PushService(db).save(
        user_id=get_settings().default_user_id,
        endpoint=payload.endpoint.strip(),
        p256dh=p256dh,
        auth=auth,
    )
    push = PushService(db)
    pending = NotificationService(db).list_pending()
    if pending:
        item = pending[0]
        body = VoiceService(db).question_for(
            amount=float(item.amount or 0),
            merchant=item.merchant,
        )
        push.notify_payment(
            title="Ledgerly",
            body=body,
            user_id=row.user_id,
            clarification_id=item.id,
        )
    else:
        push.notify_payment(
            title="Ledgerly",
            body="Alerts are on. You will get a ping after each payment.",
            user_id=row.user_id,
        )
    return {"ok": True, "id": row.id}
