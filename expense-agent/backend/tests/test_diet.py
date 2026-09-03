from datetime import date, datetime, timezone

from app.schemas.diet_schema import MealCreate, MealNL
from app.services.diet_service import DietService, compute_streak_days


def test_log_meal_and_day_totals(db):
    svc = DietService(db)
    svc.create(
        MealCreate(name="Idli sambar", meal_type="Breakfast", calories=320, protein=12),
        source="manual",
    )
    svc.create(
        MealCreate(name="Chicken biryani", meal_type="Lunch", calories=650),
        source="manual",
    )
    db.commit()
    day = svc.list_day()
    assert day["calories"] == 970
    assert day["remaining"] == day["calorie_goal"] - 970
    assert len(day["meals"]) == 2
    assert day["protein"] == 12


def test_month_goal_star_marks_hit_days(db):
    svc = DietService(db)
    svc.set_goal(2200, 120)
    svc.create(
        MealCreate(
            name="goal day",
            meal_type="Lunch",
            calories=1800,
            protein=130,
            eaten_at=datetime(2026, 8, 18, tzinfo=timezone.utc),
        ),
        source="manual",
    )
    svc.create(
        MealCreate(
            name="miss day",
            meal_type="Lunch",
            calories=2300,
            protein=100,
            eaten_at=datetime(2026, 8, 19, tzinfo=timezone.utc),
        ),
        source="manual",
    )
    db.commit()
    month = svc.list_month("2026-08")
    assert month["month"] == "2026-08"
    assert month["streak_days"] >= 0
    hit_map = {item["date"]: item["hit_goal"] for item in month["days"]}
    assert hit_map["2026-08-18"] is True
    assert hit_map["2026-08-19"] is False


def test_streak_grace_keeps_count_for_two_miss_days():
    # 30 hits ending Aug 27; miss Aug 28–29 (within grace) → still 30
    hits = {f"2026-07-{d:02d}" for d in range(29, 32)}
    hits |= {f"2026-08-{d:02d}" for d in range(1, 28)}
    assert len(hits) == 30
    state = compute_streak_days(hits, date(2026, 8, 29))
    assert state["streak_days"] == 30
    assert state["grace_misses"] == 2
    assert state["streak_broken"] is False


def test_streak_breaks_on_third_consecutive_miss():
    hits = {f"2026-07-{d:02d}" for d in range(29, 32)}
    hits |= {f"2026-08-{d:02d}" for d in range(1, 28)}
    assert len(hits) == 30
    state = compute_streak_days(hits, date(2026, 8, 30))
    assert state["streak_days"] == 0
    assert state["grace_misses"] == 3
    assert state["streak_broken"] is True
    assert state["streak_ended_length"] == 30


def test_streak_resumes_after_one_grace_miss():
    # 10 hits through Aug 20, miss Aug 21, hit Aug 22 → streak 11 (miss bridged)
    hits = {f"2026-08-{d:02d}" for d in range(11, 21)}
    hits.add("2026-08-22")
    state = compute_streak_days(hits, date(2026, 8, 22))
    assert state["streak_days"] == 11
    assert state["streak_broken"] is False


def test_streak_calendar_stars_remain_after_break(db, monkeypatch):
    svc = DietService(db)
    svc.set_goal(2200, 120)

    class FixedDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime(2026, 8, 30, 12, 0, tzinfo=tz or timezone.utc)

    monkeypatch.setattr("app.services.diet_service.datetime", FixedDateTime)

    # Hits Aug 25–27, misses Aug 28–30 → break on the 30th; stars stay for hit days
    for day in (25, 26, 27):
        svc.create(
            MealCreate(
                name=f"hit {day}",
                meal_type="Lunch",
                calories=1800,
                protein=130,
                eaten_at=datetime(2026, 8, day, 8, 0, tzinfo=timezone.utc),
            ),
            source="manual",
        )
    db.commit()
    month = svc.list_month("2026-08")
    assert month["streak_days"] == 0
    assert month["streak_broken"] is True
    assert month["streak_ended_length"] == 3
    hit_map = {item["date"]: item["hit_goal"] for item in month["days"]}
    assert hit_map["2026-08-25"] is True
    assert hit_map["2026-08-26"] is True
    assert hit_map["2026-08-27"] is True


def test_period_goal_hit_and_miss_counts(db, monkeypatch):
    svc = DietService(db)
    svc.set_goal(2200, 120)

    class FixedDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime(2026, 8, 20, 12, 0, tzinfo=tz or timezone.utc)

    monkeypatch.setattr("app.services.diet_service.datetime", FixedDateTime)

    svc.create(
        MealCreate(
            name="hit",
            meal_type="Lunch",
            calories=1800,
            protein=130,
            eaten_at=datetime(2026, 8, 18, 8, 0, tzinfo=timezone.utc),
        ),
        source="manual",
    )
    svc.create(
        MealCreate(
            name="miss",
            meal_type="Lunch",
            calories=2300,
            protein=90,
            eaten_at=datetime(2026, 8, 19, 8, 0, tzinfo=timezone.utc),
        ),
        source="manual",
    )
    db.commit()

    week = svc.period_goal_stats("week", date="2026-08-18")
    assert week["hit_days"] == 1
    assert week["missed_days"] == 3  # 17 (no log) + 19 miss + 20 (no log); today is Aug 20
    assert week["no_log_days"] == 2
    assert "hit your calorie and protein target on 1" in week["insight"]

    day_hit = svc.period_goal_stats("day", date="2026-08-18")
    assert day_hit["hit_days"] == 1
    assert day_hit["day"]["hit_goal"] is True

    day_miss = svc.period_goal_stats("day", date="2026-08-19")
    assert day_miss["hit_days"] == 0
    assert day_miss["missed_days"] == 1
    assert "did not meet" in day_miss["insight"]


def test_meal_memory_recall(db):
    svc = DietService(db)
    svc.create(
        MealCreate(
            name="my protein one scoop",
            meal_type="Breakfast",
            calories=103,
            protein=21,
            carbs=2,
            fat=1.7,
            fiber=0,
        ),
        source="manual",
    )
    db.commit()
    estimate = svc.estimate("my protein on scoop")
    assert estimate.source == "memory"
    assert estimate.calories == 103
    assert estimate.protein == 21


def test_estimate_myprotein_cookies_cream_scoop(db):
    svc = DietService(db)
    estimate = svc.estimate("my protein cookie and cream one scoop")
    assert 100 <= estimate.calories <= 110
    assert 19 <= estimate.protein <= 22
    assert estimate.carbs <= 2.4
    assert estimate.fat <= 1.9
    assert estimate.fiber == 0


def test_estimate_half_avocado_without_openai(db):
    svc = DietService(db)
    estimate = svc.estimate("avocado (half)")
    assert "avocado" in estimate.name.lower()
    assert estimate.calories == 80
    assert estimate.protein == 1.0
    assert estimate.fiber == 3.4


def test_nl_heuristic_lunch(db):
    svc = DietService(db)
    meal, reply = svc.create_from_nl(MealNL(text="Chicken biryani for lunch 650 kcal"))
    db.commit()
    assert meal.meal_type == "Lunch"
    assert meal.calories == 650
    assert "biryani" in meal.name.lower()
    assert "650" in reply
