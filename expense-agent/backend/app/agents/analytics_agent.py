"""Analytics narration over DB aggregates only — never invents numbers."""

from __future__ import annotations

import json
import time
from typing import Any, Optional

from openai import OpenAI
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.logging import get_logger
from app.prompts.category_prompt import ANALYTICS_PROMPT
from app.services.analytics_service import AnalyticsService

logger = get_logger(__name__)
_INSIGHT_CACHE: dict[tuple, tuple[float, str]] = {}
_INSIGHT_TTL_SECONDS = 120.0


class AnalyticsAgent:
    def __init__(self, db: Session):
        self.db = db
        self.settings = get_settings()
        self.analytics = AnalyticsService(db)
        self._client: Optional[OpenAI] = None

    @property
    def client(self) -> Optional[OpenAI]:
        if not self.settings.openai_api_key:
            return None
        if self._client is None:
            self._client = OpenAI(api_key=self.settings.openai_api_key)
        return self._client

    def monthly_insight(self, year: int, month: int, user_id: Optional[int] = None) -> dict[str, Any]:
        summary = self.analytics.monthly_summary(year=year, month=month, user_id=user_id)
        key = (
            year,
            month,
            round(float(summary.get("total_spent") or 0), 2),
            tuple((row.get("category"), round(float(row.get("amount") or 0), 2)) for row in summary.get("by_category") or []),
        )
        hit = _INSIGHT_CACHE.get(key)
        if hit and time.time() - hit[0] < _INSIGHT_TTL_SECONDS:
            return {"summary": summary, "insight": hit[1]}
        insight = self._narrate(summary)
        _INSIGHT_CACHE[key] = (time.time(), insight)
        return {"summary": summary, "insight": insight}

    def _narrate(self, summary: dict[str, Any]) -> str:
        # Safety: only speak using provided aggregates
        total = summary.get("total_spent", 0)
        by_cat = summary.get("by_category", [])
        lines = [f"Total spent: ₹{total:,.2f}"]
        for row in by_cat:
            lines.append(f"- {row['category']}: ₹{row['amount']:,.2f}")
        factual = "\n".join(lines)

        if not self.client:
            return factual

        try:
            response = self.client.chat.completions.create(
                model=self.settings.openai_chat_model,
                temperature=0,
                messages=[
                    {"role": "system", "content": ANALYTICS_PROMPT},
                    {
                        "role": "user",
                        "content": (
                            "Summarize this spending data in 2-4 short sentences. "
                            "Use ONLY these exact figures:\n"
                            + json.dumps(summary, default=str)
                        ),
                    },
                ],
            )
            return response.choices[0].message.content or factual
        except Exception as exc:  # noqa: BLE001
            logger.warning("Analytics narration failed: %s", exc)
            return factual
