from datetime import datetime, timezone

from app.schemas.expense_schema import ExpenseCreate
from app.services.analytics_service import AnalyticsService
from app.services.expense_service import ExpenseService


def test_analytics_totals_match_database(db):
    svc = ExpenseService(db)
    spent_at = datetime(2026, 8, 11, 12, 0, tzinfo=timezone.utc)
    svc.create(ExpenseCreate(amount=100, category="Food", spent_at=spent_at), source="manual")
    svc.create(ExpenseCreate(amount=250.5, category="Food", spent_at=spent_at), source="manual")
    svc.create(ExpenseCreate(amount=400, category="Fuel", spent_at=spent_at), source="manual")
    db.commit()

    summary = AnalyticsService(db).monthly_summary(2026, 8)
    assert summary["total_spent"] == 750.5
    by_cat = {row["category"]: row["amount"] for row in summary["by_category"]}
    assert by_cat["Food"] == 350.5
    assert by_cat["Fuel"] == 400.0
    assert summary["top_category"] == "Fuel"


def test_day_week_year_expense_windows(db):
    svc = ExpenseService(db)
    spent_at = datetime(2026, 8, 11, 12, 0, tzinfo=timezone.utc)
    svc.create(ExpenseCreate(amount=100, category="Food", spent_at=spent_at), source="manual")
    svc.create(ExpenseCreate(amount=400, category="Fuel", spent_at=spent_at), source="manual")
    db.commit()
    analytics = AnalyticsService(db)

    day = analytics.period_summary("day", date="2026-08-11")
    assert day["total_spent"] == 500.0
    assert day["top_category"] == "Fuel"
    assert "Fuel" in day["insight"]

    week = analytics.period_summary("week", date="2026-08-11")
    assert week["total_spent"] == 500.0
    assert week["top_category"] == "Fuel"
    assert "most on Fuel" in week["insight"]

    empty = analytics.period_summary("day", date="2026-08-01")
    assert empty["total_spent"] == 0
    assert empty["top_category"] is None

    year = analytics.period_summary("year", year=2026)
    assert year["total_spent"] == 500.0
    assert year["top_category"] == "Fuel"
