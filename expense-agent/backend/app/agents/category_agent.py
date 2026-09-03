"""Category classification via OpenAI with rule/prior fallbacks."""

from __future__ import annotations

import json
import re
from typing import Any, Optional

from openai import OpenAI
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.logging import get_logger
from app.prompts.category_prompt import CATEGORY_AGENT_SYSTEM, CATEGORY_FROM_USER_SYSTEM
from app.services.payment_parser import normalize_merchant_key
from app.lib.categories_match import is_weak_category
from app.lib.receiver_classify import classify_receiver

logger = get_logger(__name__)

# Always Food — even if LLM/memory would pick Groceries (Blinkit/Zepto)
FOOD_DELIVERY_BRANDS = re.compile(
    r"\b(swiggy|zomato|blinkit|zepto|dunzo|instamart)\b",
    re.I,
)

GENERIC_RULES = [
    (re.compile(r"\b(petrol|diesel|fuel|hpcl|bpcl|iocl|pump)\b", re.I), "Fuel", "Petrol", 0.85),
    (re.compile(r"\b(uber|ola|rapido|goibibo|makemytrip)\b", re.I), "Transport", "Travel", 0.88),
    (FOOD_DELIVERY_BRANDS, "Food", "Food Delivery", 0.99),
    (re.compile(r"RSP\*SWIGGY|SWIGGY\s+FOOD|\bswiggy\b", re.I), "Food", "Food Delivery", 0.99),
    (re.compile(r"\b(cafe|restaurant|bakery|pizza|biryani)\b", re.I), "Food", "Dining", 0.88),
    (re.compile(r"\b(mic mac|mcdonalds|mcd)\b", re.I), "Food", "Fast Food", 0.88),
    (re.compile(r"\b(pvr|inox|cinema|movie)\b", re.I), "Entertainment", "Movies", 0.9),
    (re.compile(r"\b(amazon|flipkart|myntra|mynt)\b", re.I), "Shopping", "Online", 0.85),
]


class CategoryAgent:
    def __init__(self, db: Session):
        self.db = db
        self.settings = get_settings()
        self._client: Optional[OpenAI] = None

    @property
    def client(self) -> Optional[OpenAI]:
        if not self.settings.openai_api_key:
            return None
        if self._client is None:
            self._client = OpenAI(api_key=self.settings.openai_api_key)
        return self._client

    def classify(
        self,
        *,
        merchant: Optional[str],
        raw_texts: list[str],
        memory: Optional[dict[str, Any]] = None,
        prior: Optional[dict[str, Any]] = None,
        preference: Optional[str] = None,
    ) -> dict[str, Any]:
        # Priority: food brands > receiver VPA > preference > memory > prior > rules > AI > Personal
        food_brand = self._food_delivery_brand(merchant=merchant, raw_texts=raw_texts)
        if food_brand:
            return food_brand

        receiver = classify_receiver(merchant, raw_texts)
        if receiver:
            return receiver

        if preference:
            parsed = self.parse_user_response(preference, merchant=merchant, amount=None)
            parsed["confidence"] = max(float(parsed.get("confidence", 0.9)), 0.95)
            parsed["source"] = "preference"
            return parsed

        if memory and memory.get("category") and not is_weak_category(memory.get("category")):
            return {
                "category": memory["category"],
                "subcategory": memory.get("subcategory"),
                "description": f"{memory.get('merchant_display') or merchant or 'Payment'}",
                "confidence": float(memory.get("confidence", 0.95)),
                "source": "memory",
            }

        if prior and prior.get("category"):
            return {
                "category": prior["category"],
                "subcategory": prior.get("subcategory"),
                "description": prior.get("merchant_display") or merchant or "Payment",
                "confidence": float(prior.get("confidence", 0.92)),
                "source": "prior",
            }

        rule = self._generic_rules(merchant=merchant, raw_texts=raw_texts)
        if rule:
            return rule

        ai = self._openai_classify(merchant=merchant, raw_texts=raw_texts)
        if ai:
            return ai

        return {
            "category": "Personal",
            "subcategory": None,
            "description": merchant or "Payment",
            "confidence": 0.8,
            "source": "fallback",
        }

    def parse_user_response(
        self,
        user_text: str,
        *,
        merchant: Optional[str],
        amount: Optional[float],
    ) -> dict[str, Any]:
        if self.client:
            try:
                content = self._chat(
                    CATEGORY_FROM_USER_SYSTEM,
                    json.dumps(
                        {"user_text": user_text, "merchant": merchant, "amount": amount},
                        default=str,
                    ),
                )
                data = self._parse_json(content)
                if data and data.get("category"):
                    data["source"] = "user_nl"
                    return data
            except Exception as exc:  # noqa: BLE001
                logger.warning("User response parse failed: %s", exc)

        return self._heuristic_user_parse(user_text, merchant)

    def _openai_classify(
        self, *, merchant: Optional[str], raw_texts: list[str]
    ) -> Optional[dict[str, Any]]:
        if not self.client:
            return self._offline_known_merchant(merchant, raw_texts)

        try:
            payload = {
                "merchant": merchant,
                "merchant_key": normalize_merchant_key(merchant),
                "raw_texts": raw_texts,
            }
            content = self._chat(CATEGORY_AGENT_SYSTEM, json.dumps(payload, default=str))
            data = self._parse_json(content)
            if data and data.get("category"):
                data["source"] = "openai"
                data["confidence"] = float(data.get("confidence", 0.5))
                return data
        except Exception as exc:  # noqa: BLE001
            logger.warning("OpenAI classify failed: %s", exc)
            return self._offline_known_merchant(merchant, raw_texts)
        return None

    def _offline_known_merchant(
        self, merchant: Optional[str], raw_texts: list[str]
    ) -> Optional[dict[str, Any]]:
        """Deterministic fallback when API key missing — used in tests/dev."""
        blob = " ".join([merchant or "", *raw_texts]).lower()
        known = {
            "pvr": ("Entertainment", "Movies", 0.98),
            "swiggy": ("Food", "Food Delivery", 0.99),
            "zomato": ("Food", "Food Delivery", 0.99),
            "blinkit": ("Food", "Food Delivery", 0.99),
            "zepto": ("Food", "Food Delivery", 0.99),
            "instamart": ("Food", "Food Delivery", 0.99),
            "hpcl": ("Fuel", "Petrol", 0.95),
            "uber": ("Transport", "Taxi", 0.97),
            "airtel": ("Recharge", "Mobile", 0.95),
            "prepaid": ("Recharge", "Mobile", 0.97),
            "jio": ("Recharge", "Mobile", 0.95),
        }
        for key, (cat, sub, conf) in known.items():
            if key in blob:
                return {
                    "category": cat,
                    "subcategory": sub,
                    "description": merchant or key.upper(),
                    "confidence": conf,
                    "source": "offline_prior",
                }
        return None

    def _food_delivery_brand(
        self, *, merchant: Optional[str], raw_texts: list[str]
    ) -> Optional[dict[str, Any]]:
        blob = " ".join([merchant or "", *raw_texts])
        match = FOOD_DELIVERY_BRANDS.search(blob)
        if not match:
            return None
        brand = match.group(1).title()
        if brand.lower() == "zomato":
            brand = "Zomato"
        elif brand.lower() == "swiggy":
            brand = "Swiggy"
        elif brand.lower() == "blinkit":
            brand = "Blinkit"
        elif brand.lower() == "zepto":
            brand = "Zepto"
        return {
            "category": "Food",
            "subcategory": "Food Delivery",
            "description": brand,
            "confidence": 0.99,
            "source": "food_brand",
        }

    def _generic_rules(
        self, *, merchant: Optional[str], raw_texts: list[str]
    ) -> Optional[dict[str, Any]]:
        blob = " ".join([merchant or "", *raw_texts])
        for pattern, category, subcategory, confidence in GENERIC_RULES:
            if pattern.search(blob):
                return {
                    "category": category,
                    "subcategory": subcategory,
                    "description": merchant or category,
                    "confidence": confidence,
                    "source": "rule",
                }
        return None

    def _heuristic_user_parse(self, text: str, merchant: Optional[str]) -> dict[str, Any]:
        lower = text.lower()
        mapping = [
            (["grocery", "groceries", "vegetables"], "Groceries", "Supermarket"),
            (["movie", "cinema", "film"], "Entertainment", "Movies"),
            (["dinner", "lunch", "breakfast", "restaurant", "food"], "Food", "Restaurants"),
            (["petrol", "diesel", "fuel"], "Fuel", "Petrol"),
            (["uber", "taxi", "cab", "ola"], "Transport", "Taxi"),
            (["car service", "vehicle", "service"], "Transport", "Vehicle Maintenance"),
            (["clothes", "clothing", "shirt"], "Shopping", "Clothing"),
            (["recharge", "prepaid", "dth"], "Recharge", "Mobile"),
        ]
        for keywords, category, subcategory in mapping:
            if any(k in lower for k in keywords):
                return {
                    "category": category,
                    "subcategory": subcategory,
                    "description": text.strip().capitalize(),
                    "confidence": 0.93,
                    "source": "user_nl_heuristic",
                }
        return {
            "category": "Other",
            "subcategory": "Miscellaneous",
            "description": text.strip().capitalize() or merchant or "Expense",
            "confidence": 0.7,
            "source": "user_nl_heuristic",
        }

    def _chat(self, system: str, user: str) -> str:
        assert self.client is not None
        response = self.client.chat.completions.create(
            model=self.settings.openai_model,
            temperature=0,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        )
        return response.choices[0].message.content or "{}"

    @staticmethod
    def _parse_json(content: str) -> Optional[dict[str, Any]]:
        try:
            return json.loads(content)
        except json.JSONDecodeError:
            match = re.search(r"\{.*\}", content, re.S)
            if match:
                try:
                    return json.loads(match.group(0))
                except json.JSONDecodeError:
                    return None
        return None
