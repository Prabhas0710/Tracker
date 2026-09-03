from datetime import datetime, timezone
from unittest.mock import patch
from zoneinfo import ZoneInfo

from app.schemas.diet_schema import MealCreate
from app.schemas.expense_schema import ExpenseCreate
from app.services.briefing_service import BriefingService
from app.services.diet_service import DietService
from app.services.expense_service import ExpenseService

IST = ZoneInfo("Asia/Kolkata")


def _spent_at(date_str: str, hour: int = 12) -> datetime:
    year, month, day = [int(part) for part in date_str.split("-")]
    return datetime(year, month, day, hour, 0, tzinfo=IST).astimezone(timezone.utc)


def test_briefing_greets_and_compares_spend(db):
    ExpenseService(db).create(
        ExpenseCreate(amount=500, category="Food", merchant="Cafe", spent_at=_spent_at("2026-08-19")),
        source="test",
    )
    ExpenseService(db).create(
        ExpenseCreate(amount=1000, category="Shopping", merchant="Store", spent_at=_spent_at("2026-08-18")),
        source="test",
    )
    DietService(db).create(
        MealCreate(
            name="Eggs",
            meal_type="Breakfast",
            calories=400,
            protein=30,
            eaten_at=_spent_at("2026-08-19"),
        ),
    )
    db.commit()

    with patch("app.services.briefing_service.today_ist", return_value="2026-08-20"):
        text = BriefingService(db).build_message()

    assert "Welcome back, Prabhas" in text
    assert "lower" in text.lower() or "₹500" in text
    assert "Diet" in text


def test_briefing_once_per_day(db):
    with patch("app.services.briefing_service.today_ist", return_value="2026-08-20"):
        first = BriefingService(db).ensure_daily_briefing()
        second = BriefingService(db).ensure_daily_briefing()

    assert first is not None
    assert "Welcome back" in first
    assert second is None


def test_briefing_festival_wish(db):
    with patch("app.services.briefing_service.today_ist", return_value="2026-08-15"):
        text = BriefingService(db).build_message()

    assert "Happy Independence Day" in text
