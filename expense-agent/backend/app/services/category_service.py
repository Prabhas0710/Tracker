"""Category taxonomy helpers."""

from __future__ import annotations

from typing import Any, Optional

from sqlalchemy.orm import Session

from app.models import Category, Expense
from sqlalchemy import distinct


class CategoryService:
    def __init__(self, db: Session):
        self.db = db

    def list_tree(self) -> list[dict[str, Any]]:
        categories = self.db.query(Category).order_by(Category.name).all()
        return [
            {
                "id": c.id,
                "name": c.name,
                "subcategories": [s.name for s in c.subcategories],
            }
            for c in categories
        ]

    def list_names(self) -> list[str]:
        named = {row[0] for row in self.db.query(Category.name).all() if row[0]}
        used = {row[0] for row in self.db.query(distinct(Expense.category)).all() if row[0]}
        return sorted(named | used, key=str.lower)

    def ensure(self, name: Optional[str]) -> None:
        trimmed = (name or "").strip()
        if not trimmed or trimmed.lower() in {"self transfer"}:
            return
        existing = self.db.query(Category).filter(Category.name.ilike(trimmed)).first()
        if existing:
            return
        self.db.add(Category(name=trimmed, description=f"{trimmed} expenses"))
        self.db.flush()
