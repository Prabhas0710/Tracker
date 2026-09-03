"""Periodic Gmail sync so new payment mails land on the dashboard quickly."""

from __future__ import annotations

import asyncio

from app.core.logging import get_logger
from app.database.database import SessionLocal
from app.services.gmail_oauth_service import GmailOAuthService
from app.services.gmail_sync_service import GmailSyncService

logger = get_logger(__name__)

SYNC_INTERVAL_SECONDS = 10


def _run_sync_once() -> None:
    db = SessionLocal()
    try:
        accounts = GmailOAuthService(db).list_credentials()
        if not accounts:
            return
        result = GmailSyncService(db).sync()
        ingested = result.get("ingested") or 0
        if ingested:
            logger.info("Background Gmail sync ingested %s new payment(s)", ingested)
    except Exception as extra:  # noqa: BLE001
        logger.warning("Background Gmail sync failed: %s", extra)
        try:
            db.rollback()
        except Exception:
            pass
    finally:
        db.close()


async def gmail_sync_loop() -> None:
    while True:
        try:
            await asyncio.to_thread(_run_sync_once)
        except asyncio.CancelledError:
            raise
        except Exception as extra:  # noqa: BLE001
            logger.warning("Background Gmail sync loop error: %s", extra)
        try:
            await asyncio.sleep(SYNC_INTERVAL_SECONDS)
        except asyncio.CancelledError:
            raise
