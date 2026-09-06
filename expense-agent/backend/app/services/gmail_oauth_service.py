"""Gmail OAuth helpers — multi-account support for one user."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Optional
from urllib.parse import urlencode

import httpx
from google.auth.exceptions import RefreshError
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.logging import get_logger
from app.models import GmailCredential

logger = get_logger(__name__)

GMAIL_SCOPES = [
    "openid",
    "https://www.googleapis.com/auth/userinfo.email",
    "https://www.googleapis.com/auth/gmail.readonly",
]


class GmailOAuthService:
    def __init__(self, db: Session):
        self.db = db
        self.settings = get_settings()

    def ensure_configured(self) -> None:
        if not self.settings.google_client_id or not self.settings.google_client_secret:
            raise ValueError("GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET must be set")

    def authorization_url(self, state: str = "expense-agent") -> str:
        self.ensure_configured()
        params = {
            "client_id": self.settings.google_client_id,
            "redirect_uri": self.settings.google_redirect_uri,
            "response_type": "code",
            "scope": " ".join(GMAIL_SCOPES),
            "access_type": "offline",
            "include_granted_scopes": "true",
            "prompt": "consent select_account",
            "state": state,
        }
        return f"https://accounts.google.com/o/oauth2/v2/auth?{urlencode(params)}"

    @staticmethod
    def _has_gmail_readonly(scope_value: str | None) -> bool:
        text = (scope_value or "").lower()
        return "gmail.readonly" in text

    def _token_can_read_gmail(self, access_token: str) -> bool:
        """Fallback when Google omits scopes from the token response."""
        try:
            with httpx.Client(timeout=20) as client:
                response = client.get(
                    "https://gmail.googleapis.com/gmail/v1/users/me/profile",
                    headers={"Authorization": f"Bearer {access_token}"},
                )
            return response.status_code < 400
        except Exception:  # noqa: BLE001
            return False

    def exchange_code(self, code: str) -> dict[str, Any]:
        self.ensure_configured()
        with httpx.Client(timeout=30) as client:
            response = client.post(
                "https://oauth2.googleapis.com/token",
                data={
                    "code": code,
                    "client_id": self.settings.google_client_id,
                    "client_secret": self.settings.google_client_secret,
                    "redirect_uri": self.settings.google_redirect_uri,
                    "grant_type": "authorization_code",
                },
            )
            response.raise_for_status()
            payload = response.json()
        granted = payload.get("scope") or ""
        access_token = payload.get("access_token") or ""
        if not self._has_gmail_readonly(granted) and not (
            access_token and self._token_can_read_gmail(access_token)
        ):
            raise ValueError(
                "Gmail readonly scope was not granted. "
                "In Google Cloud → OAuth consent screen, add scope "
                "gmail.readonly, add this email as a Test user if the app "
                "is in Testing, then Connect Gmail again and allow mail access."
            )
        if not self._has_gmail_readonly(granted) and access_token:
            # Normalize so later status/sync logic sees the expected scope.
            payload["scope"] = " ".join(GMAIL_SCOPES)
        return payload

    def fetch_user_email(self, access_token: str) -> Optional[str]:
        with httpx.Client(timeout=20) as client:
            response = client.get(
                "https://www.googleapis.com/oauth2/v2/userinfo",
                headers={"Authorization": f"Bearer {access_token}"},
            )
            if response.status_code >= 400:
                return None
            return response.json().get("email")

    def save_tokens(
        self,
        token_payload: dict[str, Any],
        user_id: Optional[int] = None,
        email: Optional[str] = None,
    ) -> GmailCredential:
        user_id = user_id or self.settings.default_user_id
        expires_in = int(token_payload.get("expires_in") or 3600)
        expiry = datetime.now(timezone.utc) + timedelta(seconds=expires_in)
        access_token = token_payload["access_token"]
        refresh_token = token_payload.get("refresh_token")
        scope = token_payload.get("scope")

        if not email:
            email = self.fetch_user_email(access_token)
        if not email:
            raise ValueError("Could not determine Gmail address for this account")

        email = email.strip().lower()
        row = (
            self.db.query(GmailCredential)
            .filter(GmailCredential.user_id == user_id, GmailCredential.email == email)
            .first()
        )
        if row:
            row.access_token = access_token
            if refresh_token:
                row.refresh_token = refresh_token
            elif not row.refresh_token:
                raise ValueError(
                    f"Google did not return a refresh token for {email}. "
                    "Disconnect and connect again, approving offline access."
                )
            row.token_expiry = expiry
            row.scopes = scope
        else:
            if not refresh_token:
                raise ValueError(
                    f"Google did not return a refresh token for {email}. "
                    "Try Connect Gmail again and approve access."
                )
            row = GmailCredential(
                user_id=user_id,
                email=email,
                access_token=access_token,
                refresh_token=refresh_token,
                token_expiry=expiry,
                scopes=scope,
            )
            self.db.add(row)
        self.db.flush()
        return row

    def clear_expired(self, user_id: Optional[int] = None) -> list[str]:
        """Remove accounts whose refresh tokens no longer work."""
        removed: list[str] = []
        for row in list(self.list_credentials(user_id=user_id)):
            try:
                self.build_google_credentials_for(row)
                self.db.commit()
            except ValueError:
                self.db.rollback()
                removed.append(row.email)
                self.db.delete(row)
                self.db.flush()
        return removed

    def list_credentials(self, user_id: Optional[int] = None) -> list[GmailCredential]:
        user_id = user_id or self.settings.default_user_id
        return (
            self.db.query(GmailCredential)
            .filter(GmailCredential.user_id == user_id)
            .order_by(GmailCredential.email.asc())
            .all()
        )

    def get_credential(
        self,
        user_id: Optional[int] = None,
        *,
        email: Optional[str] = None,
        credential_id: Optional[int] = None,
    ) -> Optional[GmailCredential]:
        user_id = user_id or self.settings.default_user_id
        q = self.db.query(GmailCredential).filter(GmailCredential.user_id == user_id)
        if credential_id is not None:
            return q.filter(GmailCredential.id == credential_id).first()
        if email:
            return q.filter(GmailCredential.email == email.strip().lower()).first()
        return q.order_by(GmailCredential.id.asc()).first()

    def status(self, user_id: Optional[int] = None) -> dict[str, Any]:
        rows = self.list_credentials(user_id=user_id)
        accounts: list[dict[str, Any]] = []
        healthy = 0
        for row in rows:
            ok = False
            error: Optional[str] = None
            try:
                self.build_google_credentials_for(row)
                self.db.commit()
                ok = True
                healthy += 1
            except ValueError as extra:
                self.db.rollback()
                error = str(extra)
            accounts.append(
                {
                    "id": row.id,
                    "email": row.email,
                    "has_refresh_token": bool(row.refresh_token),
                    "token_expiry": row.token_expiry.isoformat() if row.token_expiry else None,
                    "ok": ok,
                    "needs_reconnect": not ok,
                    "error": error,
                }
            )
        return {
            "connected": healthy > 0,
            "needs_reconnect": healthy == 0 and len(accounts) > 0,
            "count": len(accounts),
            "healthy_count": healthy,
            "email": next((a["email"] for a in accounts if a["ok"]), accounts[0]["email"] if accounts else None),
            "accounts": accounts,
        }

    def disconnect(
        self,
        user_id: Optional[int] = None,
        *,
        email: Optional[str] = None,
        credential_id: Optional[int] = None,
    ) -> bool:
        if email or credential_id is not None:
            row = self.get_credential(user_id=user_id, email=email, credential_id=credential_id)
            if not row:
                return False
            self.db.delete(row)
            self.db.flush()
            return True

        rows = self.list_credentials(user_id=user_id)
        if not rows:
            return False
        for row in rows:
            self.db.delete(row)
        self.db.flush()
        return True

    def persist_refreshed_tokens(self, row: GmailCredential, creds: Credentials) -> None:
        if creds.token:
            row.access_token = creds.token
        if creds.expiry:
            expiry = creds.expiry
            if expiry.tzinfo is None:
                expiry = expiry.replace(tzinfo=timezone.utc)
            row.token_expiry = expiry
        self.db.flush()

    def build_google_credentials_for(self, row: GmailCredential) -> Credentials:
        creds = Credentials(
            token=row.access_token,
            refresh_token=row.refresh_token,
            token_uri="https://oauth2.googleapis.com/token",
            client_id=self.settings.google_client_id,
            client_secret=self.settings.google_client_secret,
            scopes=GMAIL_SCOPES,
        )
        if row.token_expiry:
            expiry = row.token_expiry
            if expiry.tzinfo is not None:
                expiry = expiry.astimezone(timezone.utc).replace(tzinfo=None)
            creds.expiry = expiry

        if not creds.valid:
            if not creds.refresh_token:
                raise ValueError(f"Gmail token expired for {row.email}. Reconnect that account.")
            try:
                creds.refresh(Request())
            except RefreshError as extra:
                raise ValueError(
                    f"Gmail access expired for {row.email}. Reconnect that account."
                ) from extra
            self.persist_refreshed_tokens(row, creds)
        return creds
