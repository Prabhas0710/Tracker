"""Fetch bank/UPI alert emails from all connected Gmail accounts."""

from __future__ import annotations

import base64
import re
import threading
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Any, Optional

import httplib2
from google.auth.exceptions import RefreshError
from google_auth_httplib2 import AuthorizedHttp
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.logging import get_logger
from app.models import GmailCredential, GmailSyncedMessage
from app.schemas.transaction_schema import PaymentEventIn
from app.services.bank_email_parser import (
    is_bank_alert_email,
    is_cc_bill_payment_email,
    is_card_spend_alert,
    is_junk_merchant,
    is_money_movement_email,
    is_real_reference_id,
    parse_bank_email,
    parse_cc_bill_payment,
)
from app.services.credit_card_cycle_service import CreditCardCycleService, normalize_card_bank
from app.services.email_payment_filter import extract_merchant_from_email, is_likely_payment_email
from app.services.gmail_oauth_service import GmailOAuthService
from app.services.transaction_service import TransactionService

logger = get_logger(__name__)
_SYNC_LOCK = threading.Lock()


def _message_text(*, subject: str, body: str, snippet: str) -> str:
    """Combine subject, decoded body, and Gmail snippet for reliable parsing."""
    parts: list[str] = []
    if subject:
        parts.append(subject)
    if body:
        parts.append(body)
    if snippet and snippet not in body:
        parts.append(snippet)
    text = "\n".join(parts).strip()
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _decode_body(payload: dict[str, Any]) -> str:
    chunks: list[str] = []

    def walk(part: dict[str, Any]) -> None:
        mime = part.get("mimeType") or ""
        body = part.get("body") or {}
        data = body.get("data")
        if data and mime.startswith("text/"):
            try:
                chunks.append(base64.urlsafe_b64decode(data).decode("utf-8", errors="ignore"))
            except Exception:  # noqa: BLE001
                pass
        for child in part.get("parts") or []:
            walk(child)

    walk(payload)
    text = "\n".join(chunks)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _header_map(payload: dict[str, Any]) -> dict[str, str]:
    headers = payload.get("headers") or []
    return {h.get("name", "").lower(): h.get("value", "") for h in headers}


PAYMENT_SUBJECT_RE = re.compile(
    r"(transaction alert|debited|credited|upi transaction|payment received|spent on|"
    r"has been used for a transaction|credit card)",
    re.I,
)
CC_BILL_SUBJECT_RE = re.compile(r"payment received on your.*credit\s+card", re.I)


def _get_sync_record(
    db: Session, *, account_email: str, message_id: str
) -> GmailSyncedMessage | None:
    record = (
        db.query(GmailSyncedMessage)
        .filter(
            GmailSyncedMessage.gmail_account == account_email,
            GmailSyncedMessage.gmail_message_id == message_id,
        )
        .first()
    )
    if record:
        return record
    return (
        db.query(GmailSyncedMessage)
        .filter(GmailSyncedMessage.gmail_message_id == message_id)
        .first()
    )


def _mark_sync_record(
    db: Session,
    *,
    user_id: int,
    account_email: str,
    message_id: str,
    subject: str | None,
    transaction_id: int | None = None,
    existing: GmailSyncedMessage | None = None,
) -> GmailSyncedMessage:
    record = existing or _get_sync_record(
        db, account_email=account_email, message_id=message_id
    )
    if record:
        record.gmail_account = account_email
        record.subject = subject[:500] if subject else record.subject
        if transaction_id is not None:
            record.transaction_id = transaction_id
        return record
    record = GmailSyncedMessage(
        user_id=user_id,
        gmail_account=account_email,
        gmail_message_id=message_id,
        transaction_id=transaction_id,
        subject=subject[:500] if subject else None,
    )
    db.add(record)
    return record


def _should_process_message(already: GmailSyncedMessage | None) -> bool:
    """Skip only when we already ingested this Gmail message into a transaction."""
    if not already:
        return True
    return already.transaction_id is None


class GmailSyncService:
    def __init__(self, db: Session):
        self.db = db
        self.settings = get_settings()
        self.oauth = GmailOAuthService(db)

    def sync(
        self,
        user_id: Optional[int] = None,
        max_results: Optional[int] = None,
        *,
        email: Optional[str] = None,
    ) -> dict[str, Any]:
        user_id = user_id or self.settings.default_user_id
        max_results = max_results or self.settings.gmail_sync_max_results
        accounts = self.oauth.list_credentials(user_id=user_id)
        if email:
            accounts = [a for a in accounts if a.email == email.strip().lower()]
        if not accounts:
            raise ValueError("Gmail is not connected. Connect at least one Gmail account first.")

        acquired = _SYNC_LOCK.acquire(blocking=False)
        if not acquired:
            return {
                "scanned": 0,
                "ingested": 0,
                "skipped": 0,
                "failed": 0,
                "retried": 0,
                "results": [],
                "accounts": [],
                "busy": True,
                "message": "Mail sync already running",
            }
        try:
            return self._sync_locked(accounts, user_id=user_id, max_results=max_results)
        finally:
            _SYNC_LOCK.release()

    def _sync_locked(
        self,
        accounts: list[GmailCredential],
        *,
        user_id: int,
        max_results: int,
    ) -> dict[str, Any]:
        totals = {
            "scanned": 0,
            "ingested": 0,
            "skipped": 0,
            "failed": 0,
            "retried": 0,
            "results": [],
            "accounts": [],
        }
        for account in accounts:
            part = self._sync_account(account, user_id=user_id, max_results=max_results)
            totals["scanned"] += part["scanned"]
            totals["ingested"] += part["ingested"]
            totals["skipped"] += part["skipped"]
            totals["failed"] += part["failed"]
            totals["retried"] += part.get("retried", 0)
            totals["results"].extend(part["results"])
            totals["accounts"].append(
                {
                    "email": account.email,
                    "scanned": part["scanned"],
                    "ingested": part["ingested"],
                    "skipped": part["skipped"],
                    "failed": part["failed"],
                    "retried": part.get("retried", 0),
                }
            )

        self.db.commit()
        from app.services.analytics_service import AnalyticsService
        from app.services.notification_service import NotificationService

        summary = AnalyticsService(self.db).current_month_summary(user_id=user_id)
        pending = NotificationService(self.db).list_pending(user_id=user_id)
        account_names = ", ".join(a.email for a in accounts)
        totals.update(
            {
                "dashboard_total": summary.get("total_spent", 0),
                "pending_clarifications": len(pending),
                "message": (
                    f"Synced {len(accounts)} inbox(es): {account_names}. "
                    f"Scanned {totals['scanned']} · new {totals['ingested']} · "
                    f"retried {totals['retried']} · skipped {totals['skipped']} · "
                    f"need input {len(pending)} · "
                    f"dashboard ₹{float(summary.get('total_spent') or 0):,.2f}"
                ),
            }
        )
        return totals

    def _sync_account(
        self,
        account: GmailCredential,
        *,
        user_id: int,
        max_results: int,
    ) -> dict[str, Any]:
        empty = {
            "scanned": 0,
            "ingested": 0,
            "skipped": 0,
            "failed": 0,
            "retried": 0,
            "results": [],
        }
        try:
            creds = self.oauth.build_google_credentials_for(account)
        except (ValueError, RefreshError) as extra:
            logger.warning("Skipping Gmail account %s: %s", account.email, extra)
            empty["failed"] = 1
            return empty

        http = AuthorizedHttp(creds, http=httplib2.Http(timeout=12))
        service = build("gmail", "v1", http=http, cache_discovery=False)
        query = self.settings.gmail_sync_query
        messages: list[dict[str, Any]] = []
        page_token: Optional[str] = None
        try:
            for _ in range(self.settings.gmail_sync_max_pages):
                listed = (
                    service.users()
                    .messages()
                    .list(
                        userId="me",
                        q=query,
                        maxResults=max_results,
                        pageToken=page_token,
                    )
                    .execute()
                )
                messages.extend(listed.get("messages") or [])
                page_token = listed.get("nextPageToken")
                if not page_token:
                    break
        except (HttpError, RefreshError, TimeoutError, OSError) as extra:
            logger.warning("Gmail list failed for %s: %s", account.email, extra)
            empty["failed"] = 1
            return empty
        finally:
            self.oauth.persist_refreshed_tokens(account, creds)

        ingested = 0
        skipped = 0
        failed = 0
        retried = 0
        results: list[dict[str, Any]] = []
        txn_service = TransactionService(self.db)
        account_email = account.email

        for item in messages:
            message_id = item["id"]
            already = _get_sync_record(
                self.db, account_email=account_email, message_id=message_id
            )
            if not _should_process_message(already):
                skipped += 1
                continue
            if already and not already.transaction_id:
                retried += 1

            nested = self.db.begin_nested()
            try:
                full = (
                    service.users()
                    .messages()
                    .get(userId="me", id=message_id, format="full")
                    .execute()
                )
                payload = full.get("payload") or {}
                headers = _header_map(payload)
                subject = headers.get("subject", "")
                date_hdr = headers.get("date")
                body = _decode_body(payload)
                snippet = full.get("snippet") or ""
                raw_text = _message_text(subject=subject, body=body, snippet=snippet)

                ts = None
                if date_hdr:
                    try:
                        ts = parsedate_to_datetime(date_hdr)
                        if ts.tzinfo is None:
                            ts = ts.replace(tzinfo=timezone.utc)
                    except Exception:  # noqa: BLE001
                        ts = None
                if ts is None and full.get("internalDate"):
                    ts = datetime.fromtimestamp(int(full["internalDate"]) / 1000, tz=timezone.utc)

                if is_cc_bill_payment_email(subject, raw_text):
                    try:
                        bill = parse_cc_bill_payment(raw_text, timestamp=ts)
                        bank = normalize_card_bank(bill.get("card_issuer")) or "ICICI"
                        cycle_start = CreditCardCycleService(self.db).record_bill_payment(
                            user_id=user_id,
                            bank=bank,
                            paid_at=bill["paid_at"],
                            amount=bill["amount"],
                            account_suffix=bill.get("account_suffix"),
                        )
                        _mark_sync_record(
                            self.db,
                            user_id=user_id,
                            account_email=account_email,
                            message_id=message_id,
                            subject=subject,
                            existing=already,
                        )
                        results.append(
                            {
                                "gmail_account": account_email,
                                "gmail_message_id": message_id,
                                "subject": subject,
                                "type": "cc_bill_payment",
                                "bank": bank,
                                "amount": bill["amount"],
                                "cycle_start_at": cycle_start.isoformat() if cycle_start else None,
                            }
                        )
                        nested.commit()
                        continue
                    except ValueError as exc:
                        logger.warning(
                            "Bill payment parse failed for %s: %s", message_id, exc
                        )

                if not (
                    is_bank_alert_email(subject, body or snippet)
                    or is_likely_payment_email(subject, body or snippet)
                ):
                    _mark_sync_record(
                        self.db,
                        user_id=user_id,
                        account_email=account_email,
                        message_id=message_id,
                        subject=subject,
                        existing=already,
                    )
                    skipped += 1
                    nested.commit()
                    continue

                # Hard gate: must be a real credited/debited/spend mail
                if not is_money_movement_email(subject, body or snippet):
                    _mark_sync_record(
                        self.db,
                        user_id=user_id,
                        account_email=account_email,
                        message_id=message_id,
                        subject=subject,
                        existing=already,
                    )
                    skipped += 1
                    nested.commit()
                    continue

                try:
                    parsed = parse_bank_email(raw_text, timestamp=ts)
                except ValueError:
                    # Do not fall back to generic parse for declined/info/no-ref mails
                    _mark_sync_record(
                        self.db,
                        user_id=user_id,
                        account_email=account_email,
                        message_id=message_id,
                        subject=subject,
                        existing=already,
                    )
                    skipped += 1
                    nested.commit()
                    continue

                has_ref = is_real_reference_id(parsed.get("upi_ref") or parsed.get("transaction_id"))
                card_spend = is_card_spend_alert(raw_text)
                if not has_ref and not card_spend:
                    logger.info(
                        "Skipping %s — no UPI/txn ref and not a card spend (%s)",
                        message_id,
                        subject[:80],
                    )
                    _mark_sync_record(
                        self.db,
                        user_id=user_id,
                        account_email=account_email,
                        message_id=message_id,
                        subject=subject,
                        existing=already,
                    )
                    skipped += 1
                    nested.commit()
                    continue

                merchant = (
                    parsed.get("merchant")
                    or extract_merchant_from_email(raw_text)
                )
                if is_junk_merchant(merchant):
                    merchant = extract_merchant_from_email(raw_text)
                if is_junk_merchant(merchant):
                    merchant = None

                event = PaymentEventIn(
                    source="email",
                    amount=parsed["amount"],
                    merchant=merchant,
                    payment_method=parsed.get("payment_method") or "UPI",
                    transaction_id=parsed.get("transaction_id") or parsed.get("fingerprint"),
                    upi_ref=parsed.get("upi_ref"),
                    account_suffix=parsed.get("account_suffix"),
                    timestamp=parsed.get("timestamp") or ts,
                    raw_text=raw_text[:4000],
                    payload={
                        "gmail_message_id": message_id,
                        "subject": subject,
                        "gmail_account": account_email,
                        "direction": parsed.get("direction") or "debit",
                        "category": parsed.get("category"),
                        "subcategory": parsed.get("subcategory"),
                        "description": parsed.get("description"),
                        "confidence": parsed.get("confidence"),
                        "channel": parsed.get("channel"),
                        "fingerprint": parsed.get("fingerprint"),
                    },
                )
                ingest = txn_service.ingest(event, user_id=user_id)
                # If this email matched an existing payment, still record the Gmail id
                # against that same transaction so we never double-count it.
                _mark_sync_record(
                    self.db,
                    user_id=user_id,
                    account_email=account_email,
                    message_id=message_id,
                    subject=subject,
                    transaction_id=ingest.transaction.id,
                    existing=already,
                )
                if ingest.created_new:
                    ingested += 1
                else:
                    skipped += 1
                results.append(
                    {
                        "gmail_account": account_email,
                        "gmail_message_id": message_id,
                        "subject": subject,
                        "transaction_id": ingest.transaction.id,
                        "status": ingest.transaction.status,
                        "amount": ingest.transaction.amount,
                        "category": ingest.transaction.category,
                        "merged": ingest.merged,
                    }
                )
                nested.commit()
            except IntegrityError as exc:
                nested.rollback()
                logger.info(
                    "Already recorded Gmail message %s for %s: %s",
                    message_id,
                    account_email,
                    exc.orig if hasattr(exc, "orig") else exc,
                )
                skipped += 1
            except Exception as exc:  # noqa: BLE001
                nested.rollback()
                logger.warning(
                    "Failed syncing Gmail message %s for %s: %s",
                    message_id,
                    account_email,
                    exc,
                )
                failed += 1

        self.db.flush()
        self.oauth.persist_refreshed_tokens(account, creds)
        return {
            "scanned": len(messages),
            "ingested": ingested,
            "skipped": skipped,
            "failed": failed,
            "retried": retried,
            "results": results,
        }
