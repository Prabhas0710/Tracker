"""Import expenses from payment-app screenshot images (PhonePe, GPay, etc.)."""

from __future__ import annotations

import base64
import json
import re
from datetime import datetime, timedelta, timezone
from typing import Any, Optional
from zoneinfo import ZoneInfo

from openai import OpenAI
from sqlalchemy.orm import Session

from app.agents.category_agent import CategoryAgent
from app.agents.memory_agent import MemoryAgent
from app.core.config import get_settings
from app.core.logging import get_logger
from app.models import Expense
from app.schemas.expense_schema import ExpenseCreate
from app.services.expense_service import ExpenseService

logger = get_logger(__name__)
IST = ZoneInfo("Asia/Kolkata")

VISION_SYSTEM = """You extract payment transactions from screenshots of UPI / wallet apps
(PhonePe, Google Pay, Paytm, bank apps, etc.).

Return JSON only:
{
  "transactions": [
    {
      "amount": number,
      "merchant": string,
      "paid_to": string | null,
      "status": "success" | "failed" | "pending" | "unknown",
      "direction": "debit" | "credit",
      "date": "YYYY-MM-DD" | null,
      "time_hint": string | null,
      "raw_label": string | null
    }
  ]
}

Rules:
- Include every visible transaction row you can read.
- amount is a positive number in INR (strip ₹ and commas).
- merchant / paid_to: use the recipient or payer name shown (e.g. "prathis").
- status: "failed" if the row says Failed / declined / unsuccessful; otherwise "success"
  when it shows Debited / Paid / Credited / Successful.
- direction: "debit" for Paid to / Debited / sent; "credit" for Received / Credited.
- date: absolute calendar date when visible (e.g. "02 Jul 2020" → "2020-07-02").
  For relative times like "1 min ago", "Today", set date to null and put the text in time_hint.
- Skip headers, filters, and non-transaction UI chrome.
- If nothing readable, return {"transactions": []}.
"""


class ScreenshotImportService:
    def __init__(self, db: Session):
        self.db = db
        self.settings = get_settings()

    def import_image(
        self,
        data: bytes,
        *,
        filename: str = "screenshot.png",
        content_type: str = "image/png",
    ) -> dict[str, Any]:
        if not data:
            return {
                "ok": False,
                "reply": "That image was empty — try again.",
                "added": [],
                "skipped": [],
                "failed_rows": 0,
            }

        extracted = self._extract(data, content_type=content_type, filename=filename)
        rows = extracted.get("transactions") or []
        if not rows:
            return {
                "ok": False,
                "reply": "I couldn’t find any transactions in that image. Try a clearer screenshot.",
                "added": [],
                "skipped": [],
                "failed_rows": 0,
            }

        added: list[dict[str, Any]] = []
        skipped: list[dict[str, Any]] = []
        failed_rows = 0
        expense_svc = ExpenseService(self.db)
        category_agent = CategoryAgent(self.db)
        memory = MemoryAgent(self.db)
        today = datetime.now(IST).date()

        for row in rows:
            status = str(row.get("status") or "unknown").lower()
            if status == "failed":
                failed_rows += 1
                skipped.append(
                    {
                        "reason": "failed",
                        "amount": row.get("amount"),
                        "merchant": row.get("merchant") or row.get("paid_to"),
                    }
                )
                continue

            direction = str(row.get("direction") or "debit").lower()
            if direction == "credit":
                skipped.append(
                    {
                        "reason": "credit",
                        "amount": row.get("amount"),
                        "merchant": row.get("merchant") or row.get("paid_to"),
                    }
                )
                continue

            try:
                amount = float(row.get("amount"))
            except (TypeError, ValueError):
                skipped.append({"reason": "bad_amount", "raw": row})
                continue
            if amount <= 0:
                skipped.append({"reason": "bad_amount", "amount": amount})
                continue

            merchant = (
                (row.get("merchant") or row.get("paid_to") or row.get("raw_label") or "Unknown")
                .strip()
            )[:120]
            spent_at = self._resolve_spent_at(row.get("date"), row.get("time_hint"), today)

            if self._is_duplicate(merchant=merchant, amount=amount, spent_at=spent_at):
                skipped.append(
                    {"reason": "duplicate", "amount": amount, "merchant": merchant}
                )
                continue

            classified = category_agent.classify(
                merchant=merchant,
                raw_texts=[
                    str(row.get("raw_label") or ""),
                    f"Paid to {merchant}",
                    f"₹{amount}",
                ],
                memory=memory.lookup(merchant).get("memory"),
            )
            expense = expense_svc.create(
                ExpenseCreate(
                    amount=amount,
                    category=classified.get("category") or "Other",
                    subcategory=classified.get("subcategory"),
                    description=classified.get("description")
                    or f"Paid to {merchant} (from screenshot)",
                    merchant=merchant,
                    spent_at=spent_at,
                ),
                source="screenshot",
            )
            expense.direction = "debit"
            expense.confidence = float(classified.get("confidence") or 0.75)
            memory.learn(
                merchant=merchant,
                category=expense.category,
                subcategory=expense.subcategory,
            )
            added.append(
                {
                    "id": expense.id,
                    "amount": float(expense.amount),
                    "merchant": expense.merchant,
                    "category": expense.category,
                    "spent_at": expense.spent_at.astimezone(IST).strftime("%Y-%m-%d"),
                }
            )

        self.db.commit()
        reply = self._build_reply(added=added, skipped=skipped, failed_rows=failed_rows)
        return {
            "ok": bool(added),
            "reply": reply,
            "added": added,
            "skipped": skipped,
            "failed_rows": failed_rows,
        }

    def _extract(self, data: bytes, *, content_type: str, filename: str) -> dict[str, Any]:
        if not self.settings.openai_api_key:
            raise RuntimeError("OpenAI is not configured, so I can’t read screenshots yet.")
        mime = content_type or "image/png"
        if mime == "application/octet-stream":
            lower = filename.lower()
            if lower.endswith(".jpg") or lower.endswith(".jpeg"):
                mime = "image/jpeg"
            elif lower.endswith(".webp"):
                mime = "image/webp"
            else:
                mime = "image/png"
        b64 = base64.b64encode(data).decode("ascii")
        client = OpenAI(api_key=self.settings.openai_api_key)
        model = self.settings.openai_chat_model or self.settings.openai_model or "gpt-4o"
        response = client.chat.completions.create(
            model=model,
            temperature=0,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": VISION_SYSTEM},
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": (
                                "Read every transaction in this screenshot and return JSON. "
                                f"Today in Asia/Kolkata is {datetime.now(IST).date().isoformat()}."
                            ),
                        },
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:{mime};base64,{b64}"},
                        },
                    ],
                },
            ],
        )
        raw = response.choices[0].message.content or "{}"
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            logger.warning("Vision JSON parse failed: %s", raw[:400])
            return {"transactions": []}

    def _resolve_spent_at(
        self,
        date_str: Optional[str],
        time_hint: Optional[str],
        today,
    ) -> datetime:
        if date_str:
            try:
                day = datetime.strptime(str(date_str)[:10], "%Y-%m-%d").date()
                return datetime(day.year, day.month, day.day, 12, 0, tzinfo=IST).astimezone(
                    timezone.utc
                )
            except ValueError:
                pass

        hint = (time_hint or "").lower()
        if hint:
            if "yesterday" in hint:
                day = today - timedelta(days=1)
                return datetime(day.year, day.month, day.day, 12, 0, tzinfo=IST).astimezone(
                    timezone.utc
                )
            rel = re.search(r"(\d+)\s*(min|minute|hour|hr|day)s?\s*ago", hint)
            if rel:
                n = int(rel.group(1))
                unit = rel.group(2)
                delta = (
                    timedelta(minutes=n)
                    if unit.startswith("min")
                    else timedelta(hours=n)
                    if unit.startswith("h")
                    else timedelta(days=n)
                )
                return (datetime.now(IST) - delta).astimezone(timezone.utc)
            if "today" in hint or "just now" in hint or "sec" in hint:
                return datetime.now(timezone.utc)

        return datetime(today.year, today.month, today.day, 12, 0, tzinfo=IST).astimezone(
            timezone.utc
        )

    def _is_duplicate(self, *, merchant: str, amount: float, spent_at: datetime) -> bool:
        local = spent_at.astimezone(IST)
        start = datetime(local.year, local.month, local.day, tzinfo=IST).astimezone(timezone.utc)
        end = start + timedelta(days=1)
        rows = (
            self.db.query(Expense)
            .filter(
                Expense.user_id == self.settings.default_user_id,
                Expense.spent_at >= start,
                Expense.spent_at < end,
            )
            .all()
        )
        key = merchant.strip().lower()
        for row in rows:
            if abs(float(row.amount) - amount) < 0.01 and (row.merchant or "").strip().lower() == key:
                return True
        return False

    def _build_reply(
        self,
        *,
        added: list[dict[str, Any]],
        skipped: list[dict[str, Any]],
        failed_rows: int,
    ) -> str:
        if not added and failed_rows and not any(s.get("reason") != "failed" for s in skipped):
            return (
                f"I found {failed_rows} failed transaction"
                f"{'s' if failed_rows != 1 else ''} and skipped them — nothing was added."
            )
        if not added:
            reasons = {s.get("reason") for s in skipped}
            if "duplicate" in reasons:
                return "Those transactions look like ones already in Expenses — nothing new to add."
            return "I read the screenshot but didn’t add any new debit expenses."

        lines = [f"Added {len(added)} expense{'s' if len(added) != 1 else ''} from your screenshot:"]
        for item in added[:12]:
            lines.append(
                f"• ₹{item['amount']:,.0f} → {item['merchant']} ({item['category']}) on {item['spent_at']}"
            )
        if len(added) > 12:
            lines.append(f"• …and {len(added) - 12} more")
        notes = []
        if failed_rows:
            notes.append(f"skipped {failed_rows} failed")
        dupes = sum(1 for s in skipped if s.get("reason") == "duplicate")
        if dupes:
            notes.append(f"skipped {dupes} duplicate{'s' if dupes != 1 else ''}")
        credits = sum(1 for s in skipped if s.get("reason") == "credit")
        if credits:
            notes.append(f"skipped {credits} credit{'s' if credits != 1 else ''}")
        if notes:
            lines.append("(" + "; ".join(notes) + ")")
        return "\n".join(lines)
