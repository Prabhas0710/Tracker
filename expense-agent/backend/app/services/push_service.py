"""Web Push so the phone can alert while PhonePe or the home screen is open."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.logging import get_logger
from app.models.push import PushSubscription

logger = get_logger(__name__)


class PushService:
    def __init__(self, db: Session):
        self.db = db
        self.settings = get_settings()

    def _vapid(self):
        from py_vapid import Vapid

        raw = self._private_key()
        if raw.startswith("-----"):
            return Vapid.from_string(private_key=raw)
        return Vapid.from_file(private_key_file=raw)

    def public_key(self) -> str:
        from cryptography.hazmat.primitives import serialization
        from py_vapid.utils import b64urlencode

        try:
            raw = self._vapid().public_key.public_bytes(
                serialization.Encoding.X962,
                serialization.PublicFormat.UncompressedPoint,
            )
            return b64urlencode(raw)
        except Exception:
            return (self.settings.vapid_public_key or "").strip()

    def _private_key(self) -> str:
        raw = (self.settings.vapid_private_key or "").strip().strip('"').replace("\\n", "\n")
        if raw.startswith("-----"):
            return raw
        path = Path(raw)
        if not path.is_file():
            path = Path(__file__).resolve().parents[2] / raw
        return str(path)

    def save(self, *, user_id: int, endpoint: str, p256dh: str, auth: str) -> PushSubscription:
        row = (
            self.db.query(PushSubscription)
            .filter(PushSubscription.endpoint == endpoint)
            .first()
        )
        if row:
            row.user_id = user_id
            row.p256dh = p256dh
            row.auth = auth
        else:
            row = PushSubscription(
                user_id=user_id,
                endpoint=endpoint,
                p256dh=p256dh,
                auth=auth,
            )
            self.db.add(row)
        self.db.commit()
        self.db.refresh(row)
        return row

    def notify_payment(
        self,
        *,
        title: str,
        body: str,
        user_id: Optional[int] = None,
        clarification_id: Optional[int] = None,
        url: Optional[str] = None,
    ) -> int:
        if not self.settings.vapid_private_key or not self.settings.vapid_public_key:
            return 0
        user_id = user_id or self.settings.default_user_id
        rows = (
            self.db.query(PushSubscription)
            .filter(PushSubscription.user_id == user_id)
            .all()
        )
        sent = 0
        for row in rows:
            if self._send(
                row,
                title=title,
                body=body,
                clarification_id=clarification_id,
                url=url,
            ):
                sent += 1
        logger.info("Push notify '%s' → %s/%s device(s)", title, sent, len(rows))
        return sent

    def _send(
        self,
        row: PushSubscription,
        *,
        title: str,
        body: str,
        clarification_id: Optional[int] = None,
        url: Optional[str] = None,
    ) -> bool:
        try:
            from pywebpush import WebPushException, webpush

            payload = {
                "title": title,
                "body": body,
                "url": url
                or (
                    f"/dashboard?ask=1&cid={clarification_id}"
                    if clarification_id
                    else "/dashboard?ask=1"
                ),
            }
            if clarification_id:
                payload["clarification_id"] = clarification_id
            webpush(
                subscription_info={
                    "endpoint": row.endpoint,
                    "keys": {"p256dh": row.p256dh, "auth": row.auth},
                },
                data=json.dumps(payload),
                vapid_private_key=self._vapid(),
                vapid_claims={
                    "sub": self.settings.vapid_mailto
                    if self.settings.vapid_mailto.startswith("mailto:")
                    else f"mailto:{self.settings.vapid_mailto}",
                },
            )
            return True
        except Exception as extra:  # noqa: BLE001
            gone = False
            try:
                from pywebpush import WebPushException

                gone = isinstance(extra, WebPushException) and getattr(extra, "response", None) is not None
                if gone:
                    status = extra.response.status_code  # type: ignore[union-attr]
                    gone = status in {404, 410}
            except Exception:
                gone = False
            if gone:
                self.db.delete(row)
                self.db.commit()
            else:
                logger.warning("Push notify failed: %s", extra)
            return False
