from urllib.parse import quote, urlparse

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import RedirectResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.database.database import get_db
from app.services.gmail_oauth_service import GmailOAuthService
from app.services.gmail_sync_service import GmailSyncService

router = APIRouter(prefix="/api/auth/gmail", tags=["gmail"])


class DisconnectBody(BaseModel):
    email: str | None = None
    credential_id: int | None = None


def _safe_frontend_url(candidate: str | None) -> str:
    settings = get_settings()
    fallback = settings.frontend_url.rstrip("/")
    if not candidate:
        return fallback
    parsed = urlparse(candidate)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        return fallback
    host = parsed.hostname
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    origin = f"{parsed.scheme}://{host}" + (f":{port}" if parsed.port else "")
    allowed = {o.rstrip("/") for o in settings.cors_origin_list}
    if origin in allowed:
        return origin
    private = (
        host in {"localhost", "127.0.0.1"}
        or host.startswith("192.168.")
        or host.startswith("10.")
    )
    if private and port in {3000, 3005}:
        return origin
    return fallback


@router.get("/status")
def gmail_status(db: Session = Depends(get_db)):
    return GmailOAuthService(db).status()


@router.get("/login")
def gmail_login(request: Request, db: Session = Depends(get_db)):
    referer = request.headers.get("referer") or ""
    parsed = urlparse(referer)
    frontend = _safe_frontend_url(
        f"{parsed.scheme}://{parsed.netloc}" if parsed.scheme and parsed.netloc else None
    )
    try:
        url = GmailOAuthService(db).authorization_url(state=frontend)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return RedirectResponse(url)


@router.post("/reconnect")
def gmail_reconnect(request: Request, db: Session = Depends(get_db)):
    """Drop stored Gmail tokens, then return a fresh Google OAuth URL."""
    referer = request.headers.get("referer") or ""
    parsed = urlparse(referer)
    frontend = _safe_frontend_url(
        f"{parsed.scheme}://{parsed.netloc}" if parsed.scheme and parsed.netloc else None
    )
    oauth = GmailOAuthService(db)
    accounts = oauth.list_credentials()
    cleared = [row.email for row in accounts]
    oauth.disconnect()
    db.commit()
    try:
        url = oauth.authorization_url(state=frontend)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"login_url": url, "cleared": cleared, "frontend": frontend}


@router.get("/callback")
def gmail_callback(
    code: str | None = None,
    error: str | None = None,
    state: str | None = None,
    db: Session = Depends(get_db),
):
    frontend = _safe_frontend_url(state)
    if error:
        return RedirectResponse(f"{frontend}/expenses?gmail=error&reason={quote(error)}")
    if not code:
        raise HTTPException(status_code=400, detail="Missing authorization code")

    oauth = GmailOAuthService(db)
    try:
        tokens = oauth.exchange_code(code)
        saved = oauth.save_tokens(tokens)
        db.commit()
    except Exception as exc:  # noqa: BLE001
        db.rollback()
        return RedirectResponse(
            f"{frontend}/expenses?gmail=error&reason={quote(str(exc)[:180])}"
        )
    return RedirectResponse(
        f"{frontend}/expenses?gmail=connected&email={quote(saved.email or '')}"
    )


@router.post("/disconnect")
def gmail_disconnect(payload: DisconnectBody | None = None, db: Session = Depends(get_db)):
    payload = payload or DisconnectBody()
    removed = GmailOAuthService(db).disconnect(
        email=payload.email,
        credential_id=payload.credential_id,
    )
    db.commit()
    return {"disconnected": removed, "email": payload.email, "credential_id": payload.credential_id}


@router.post("/sync")
def gmail_sync(
    max_results: int = Query(default=100, ge=1, le=200),
    email: str | None = Query(default=None),
    db: Session = Depends(get_db),
):
    try:
        result = GmailSyncService(db).sync(max_results=max_results, email=email)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"Gmail sync failed: {exc}") from exc
    return result
