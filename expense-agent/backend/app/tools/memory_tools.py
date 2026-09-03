from typing import Any, Optional

from sqlalchemy.orm import Session

from app.agents.memory_agent import MemoryAgent


def lookup_merchant_memory(
    db: Session, merchant: str, user_id: Optional[int] = None
) -> dict[str, Any]:
    return MemoryAgent(db).lookup(merchant, user_id=user_id)


def learn_merchant(
    db: Session,
    merchant: str,
    category: str,
    subcategory: Optional[str] = None,
    user_id: Optional[int] = None,
) -> dict[str, Any]:
    memory = MemoryAgent(db).learn(
        merchant=merchant,
        category=category,
        subcategory=subcategory,
        user_id=user_id,
    )
    if not memory:
        return {}
    return {
        "merchant_key": memory.merchant_key,
        "category": memory.category,
        "subcategory": memory.subcategory,
        "confidence": memory.confidence,
    }
