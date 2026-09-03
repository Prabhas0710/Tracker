from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.agents.analytics_agent import AnalyticsAgent
from app.database.database import get_db
from app.services.analytics_service import AnalyticsService
from app.services.category_service import CategoryService
from app.services.diet_service import DietService

router = APIRouter(prefix="/api", tags=["analytics"])


@router.get("/analytics/summary")
def analytics_summary(
    year: int | None = None,
    month: int | None = None,
    period: str | None = Query(default=None),
    date: str | None = Query(default=None, description="YYYY-MM-DD in IST"),
    db: Session = Depends(get_db),
):
    try:
        from zoneinfo import ZoneInfo

        now = datetime.now(ZoneInfo("Asia/Kolkata"))
    except Exception:
        now = datetime.now(timezone.utc)
    year = year or now.year
    month = month or now.month
    period_name = (period or "month").lower()
    analytics = AnalyticsService(db)
    summary = analytics.period_summary(period_name, date=date, year=year, month=month)
    diet = DietService(db).period_goal_stats(
        period_name, date=date, year=year, month=month
    )
    if period_name == "month":
        insight = AnalyticsAgent(db).monthly_insight(year, month).get("insight")
        if insight:
            summary["insight"] = insight
    return {**summary, "diet": diet}


@router.get("/categories")
def list_categories(db: Session = Depends(get_db)):
    return CategoryService(db).list_tree()


@router.get("/categories/names")
def list_category_names(db: Session = Depends(get_db)):
    return CategoryService(db).list_names()
