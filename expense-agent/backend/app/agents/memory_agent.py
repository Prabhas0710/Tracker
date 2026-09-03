"""Merchant memory and user preference lookup/learning."""

from __future__ import annotations

from typing import Any, Optional

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.lib.categories_match import is_weak_category
from app.models import MerchantMemory, MerchantPrior, UserPreference
from app.services.payment_parser import normalize_merchant_key


class MemoryAgent:
    def __init__(self, db: Session):
        self.db = db
        self.settings = get_settings()

    def lookup(
        self, merchant: Optional[str], user_id: Optional[int] = None
    ) -> dict[str, Any]:
        user_id = user_id or self.settings.default_user_id
        key = normalize_merchant_key(merchant)
        result: dict[str, Any] = {
            "memory": None,
            "prior": None,
            "preference": None,
        }
        if not key:
            return result

        pref = (
            self.db.query(UserPreference)
            .filter(
                UserPreference.user_id == user_id,
                UserPreference.key.in_([f"merchant:{key}", f"merchant_category:{key}"]),
            )
            .order_by(UserPreference.id.desc())
            .first()
        )
        if pref:
            result["preference"] = pref.value

        memory = (
            self.db.query(MerchantMemory)
            .filter(MerchantMemory.user_id == user_id, MerchantMemory.merchant_key == key)
            .first()
        )
        if memory:
            result["memory"] = {
                "merchant_key": memory.merchant_key,
                "merchant_display": memory.merchant_display,
                "category": memory.category,
                "subcategory": memory.subcategory,
                "confidence": memory.confidence,
            }

        # Try exact and partial prior match
        prior = self.db.query(MerchantPrior).filter(MerchantPrior.merchant_key == key).first()
        if not prior:
            priors = self.db.query(MerchantPrior).all()
            for p in priors:
                if p.merchant_key in key or key in p.merchant_key:
                    prior = p
                    break
        if prior:
            result["prior"] = {
                "merchant_key": prior.merchant_key,
                "merchant_display": prior.merchant_display,
                "category": prior.category,
                "subcategory": prior.subcategory,
                "confidence": prior.confidence,
            }
        return result

    def learn(
        self,
        *,
        merchant: Optional[str],
        category: str,
        subcategory: Optional[str],
        confidence: float = 0.95,
        user_id: Optional[int] = None,
    ) -> Optional[MerchantMemory]:
        user_id = user_id or self.settings.default_user_id
        key = normalize_merchant_key(merchant)
        if not key:
            return None
        if is_weak_category(category):
            return None

        memory = (
            self.db.query(MerchantMemory)
            .filter(MerchantMemory.user_id == user_id, MerchantMemory.merchant_key == key)
            .first()
        )
        if memory:
            memory.category = category
            memory.subcategory = subcategory
            memory.confidence = confidence
            memory.hit_count = (memory.hit_count or 0) + 1
            memory.merchant_display = merchant or memory.merchant_display
        else:
            memory = MerchantMemory(
                user_id=user_id,
                merchant_key=key,
                merchant_display=merchant or key,
                category=category,
                subcategory=subcategory,
                confidence=confidence,
                hit_count=1,
                is_seed_prior=False,
            )
            self.db.add(memory)
        self.db.flush()
        return memory
