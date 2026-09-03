"""OpenAI speech for unclear-payment category questions."""

from __future__ import annotations

import io
import re
from typing import Optional

from openai import OpenAI

from app.core.config import get_settings
from app.core.logging import get_logger
from app.lib.categories_match import match_spoken_category
from app.services.category_service import CategoryService

logger = get_logger(__name__)

FILLER = re.compile(
    r"\b(um+|uh+|please|keep( it)?( as)?|put( it)?( in| under)?|category|this is|it's|its|as)\b",
    re.I,
)


class VoiceService:
    def __init__(self, db=None):
        self.settings = get_settings()
        self.db = db
        self._client: Optional[OpenAI] = None

    @property
    def client(self) -> OpenAI:
        if not self.settings.openai_api_key:
            raise RuntimeError("OPENAI_API_KEY is not set")
        if self._client is None:
            self._client = OpenAI(api_key=self.settings.openai_api_key)
        return self._client

    def speak(self, text: str) -> bytes:
        spoken = (text or "").strip()
        if not spoken:
            raise ValueError("Nothing to speak")
        response = self.client.audio.speech.create(
            model=self.settings.openai_tts_model,
            voice=self.settings.openai_tts_voice,
            input=spoken[:4000],
            response_format="mp3",
        )
        return response.content

    def transcribe(self, data: bytes, filename: str = "audio.webm", content_type: str = "audio/webm") -> str:
        if not data:
            return ""
        prompt = "Food, Entertainment, Personal, Shopping, Groceries, Other, Bills, Recharge, Fuel, Transport, Health."

        def _run(model: str) -> str:
            buf = io.BytesIO(data)
            buf.name = filename
            result = self.client.audio.transcriptions.create(
                model=model,
                file=buf,
                language="en",
                prompt=prompt,
            )
            return (getattr(result, "text", None) or "").strip()

        try:
            return _run(self.settings.openai_stt_model)
        except Exception as extra:  # noqa: BLE001
            logger.warning("STT %s failed (%s); falling back to whisper-1", self.settings.openai_stt_model, extra)
            return _run("whisper-1")

    def question_for(self, *, amount: float, merchant: Optional[str]) -> str:
        who = (merchant or "an unknown merchant").strip()
        rupees = f"{amount:,.0f}" if float(amount).is_integer() else f"{amount:,.2f}"
        return (
            f"₹{rupees} to {who}. Food, Entertainment, Personal, or type another category?"
        )

    def retry_prompt(self) -> str:
        return "Sorry, I didn't catch that. Which category should I keep this in?"

    def saved_prompt(self, category: str) -> str:
        return f"Saved as {category}."

    def leftover_prompt(self) -> str:
        return "No answer, so I saved this as Personal."

    def match_category(self, spoken: str) -> Optional[str]:
        known: list[str] = []
        if self.db is not None:
            try:
                known = CategoryService(self.db).list_names()
            except Exception as exc:  # noqa: BLE001
                logger.warning("Could not load category names: %s", exc)
        cleaned = FILLER.sub(" ", spoken or "")
        cleaned = re.sub(r"\s+", " ", cleaned).strip()
        if not cleaned:
            return None
        return match_spoken_category(cleaned, known)
