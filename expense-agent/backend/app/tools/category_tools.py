from typing import Any

from sqlalchemy.orm import Session

from app.services.category_service import CategoryService


def get_category_tree(db: Session) -> list[dict[str, Any]]:
    return CategoryService(db).list_tree()
