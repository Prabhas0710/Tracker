from typing import Any, Optional

from sqlalchemy.orm import Session

from app.services.analytics_service import AnalyticsService


def monthly_totals(db: Session, year: int, month: int, user_id: Optional[int] = None) -> dict[str, Any]:
    """Return SQL SUM aggregates only — never estimate."""
    return AnalyticsService(db).monthly_summary(year, month, user_id=user_id)
