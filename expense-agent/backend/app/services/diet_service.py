"""Daily meal log and calorie totals."""

from __future__ import annotations

import json
import re
from datetime import datetime, timedelta, timezone
from typing import Any, Optional
from zoneinfo import ZoneInfo

from openai import OpenAI
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.logging import get_logger
from app.models.meal import Meal
from app.models.meal_memory import MealMemory
from app.models.user_preference import UserPreference
from app.schemas.diet_schema import MealCreate, MealEstimateOut, MealNL, MealOut, MealUpdate

logger = get_logger(__name__)
IST = ZoneInfo("Asia/Kolkata")
GOAL_KEY = "diet_calorie_goal"
PROTEIN_GOAL_KEY = "diet_protein_goal"
WATER_GOAL_KEY = "diet_water_goal_ml"
STREAK_BREAK_NOTIFIED_KEY = "diet_streak_break_notified_on"
DEFAULT_GOAL = 2200.0
DEFAULT_PROTEIN_GOAL = 120.0
DEFAULT_WATER_GOAL_ML = 3000.0  # 3 liters
# Miss the daily goal this many days in a row without breaking the streak.
# Breaks on the next miss (more than two continuous miss days).
STREAK_GRACE_MISS_DAYS = 2
STREAK_LOOKBACK_DAYS = 400
MEAL_TYPES = ("Breakfast", "Lunch", "Dinner", "Snack")


def _water_pref_key(date_str: str) -> str:
    return f"diet_water_ml:{date_str}"

NL_SYSTEM = """You parse a meal log into JSON only:
{
  "name": string,
  "meal_type": "Breakfast" | "Lunch" | "Dinner" | "Snack",
  "calories": number,
  "protein": number | null,
  "carbs": number | null,
  "fat": number | null,
  "fiber": number | null
}
Indian food is common. Estimate calories and macros if the user omitted them. Never invent a meal they did not mention.
"""

ESTIMATE_SYSTEM = """You estimate nutrition from a food name and quantity. Return JSON only:
{
  "name": string,
  "calories": number,
  "protein": number,
  "carbs": number,
  "fat": number,
  "fiber": number
}
Rules:
- Values MUST be for the amount they wrote, not per 100g.
- If they name a brand + product + flavor, use that product's published nutrition label, not a generic food of the same type.
- Protein powder "1 scoop" is the label scoop (usually 25–32g), not a 40g gym scoop and not a ready-to-drink shake.
- Myprotein Impact Whey Protein (Cookies & Cream and most flavors), 1 scoop / 25g: about 103 kcal, 21 g protein, 2 g carbs, 1.7 g fat, 0 g fiber.
- Myprotein Impact Whey Isolate, 1 scoop / 25g: about 93 kcal, 23 g protein, 0.6 g carbs, 0.3 g fat, 0 g fiber.
- If they do not say Isolate, use Impact Whey Protein, not Isolate, and do not inflate to 120 kcal / 24 g.
- Scale half, 1/2, 2 scoops, 100g, 1 bowl, 1 katori, 1 cup, 1 piece.
- If quantity is missing, use one typical serving / one label scoop.
- Homemade Indian food: use typical homemade or restaurant values.
- Round calories to a whole number, macros to 1 decimal.
"""

# Brand label values take priority over the model so scoops match the tub, not a guess.
# kcal, protein, carbs, fat, fiber — one label scoop.
_BRANDED_SCOOPS: list[tuple[tuple[str, ...], tuple[float, float, float, float, float], str]] = [
    (
        ("myprotein", "cookies", "isolate"),
        (93, 23.0, 0.6, 0.3, 0.0),
        "Myprotein Impact Whey Isolate Cookies & Cream",
    ),
    (
        ("myprotein", "cookie", "isolate"),
        (93, 23.0, 0.6, 0.3, 0.0),
        "Myprotein Impact Whey Isolate Cookies & Cream",
    ),
    (
        ("myprotein", "cookies"),
        (103, 21.0, 2.0, 1.7, 0.0),
        "Myprotein Impact Whey Protein Cookies & Cream",
    ),
    (
        ("myprotein", "cookie"),
        (103, 21.0, 2.0, 1.7, 0.0),
        "Myprotein Impact Whey Protein Cookies & Cream",
    ),
    (
        ("myprotein", "isolate"),
        (93, 23.0, 0.6, 0.3, 0.0),
        "Myprotein Impact Whey Isolate",
    ),
    (("myprotein",), (103, 21.0, 1.1, 1.9, 0.0), "Myprotein Impact Whey Protein"),
]


def _food_key(text: str) -> str:
    compact = (text or "").lower().replace("&", "and")
    compact = compact.replace("my protein", "myprotein")
    return re.sub(r"[^a-z0-9]+", "", compact)


def _memory_key(text: str) -> str:
    """Normalize food text so repeat logs match (typos, one/on scoop, filler words)."""
    compact = (text or "").lower().replace("&", "and")
    compact = compact.replace("my protein", "myprotein")
    compact = re.sub(r"\bon\s+scoop\b", "one scoop", compact)
    compact = re.sub(r"\b(one|a|an|the|for|at)\b", " ", compact)
    return re.sub(r"[^a-z0-9]+", "", compact)


def _scoop_multiplier(text: str) -> float:
    lower = (text or "").lower()
    if re.search(r"\b(half|1/2|½)\s*scoop", lower):
        return 0.5
    match = re.search(r"(\d+(?:\.\d+)?)\s*scoops?\b", lower)
    if match:
        return float(match.group(1))
    grams = re.search(r"(\d+(?:\.\d+)?)\s*g\b", lower)
    if grams:
        return float(grams.group(1)) / 25.0
    return 1.0


def _branded_estimate(text: str) -> dict[str, Any] | None:
    haystack = _food_key(text)
    if not haystack:
        return None
    for tokens, macros, name in _BRANDED_SCOOPS:
        if all(token in haystack for token in tokens):
            scoops = _scoop_multiplier(text)
            calories, protein, carbs, fat, fiber = (value * scoops for value in macros)
            return {
                "name": name,
                "calories": calories,
                "protein": protein,
                "carbs": carbs,
                "fat": fat,
                "fiber": fiber,
            }
    return None


# Typical one-serving macros used only when OpenAI is unavailable.
# kcal, protein, carbs, fat, fiber
_FOOD_HINTS: list[tuple[tuple[str, ...], tuple[float, float, float, float, float]]] = [
    (("avocado",), (160, 2.0, 8.5, 14.7, 6.7)),
    (("idli",), (58, 2.0, 12.0, 0.4, 0.8)),
    (("dosa",), (133, 2.6, 18.0, 5.2, 1.0)),
    (("sambar",), (80, 4.0, 12.0, 2.0, 3.0)),
    (("biryani",), (320, 14.0, 42.0, 10.0, 2.0)),
    (("roti", "chapati"), (120, 3.5, 18.0, 3.7, 2.0)),
    (("rice",), (206, 4.3, 45.0, 0.4, 0.6)),
    (("egg",), (78, 6.3, 0.6, 5.3, 0.0)),
    (("chicken",), (165, 31.0, 0.0, 3.6, 0.0)),
    (("curd", "yogurt", "dahi"), (98, 5.3, 7.4, 5.0, 0.0)),
]


def day_bounds(date_str: str) -> tuple[datetime, datetime]:
    year, month, day = [int(part) for part in date_str.split("-")]
    start = datetime(year, month, day, tzinfo=IST).astimezone(timezone.utc)
    end = (datetime(year, month, day, tzinfo=IST) + timedelta(days=1)).astimezone(timezone.utc)
    return start, end


def today_ist() -> str:
    now = datetime.now(IST)
    return f"{now.year:04d}-{now.month:02d}-{now.day:02d}"


def day_hit_goal(
    calories: float,
    protein: float,
    calorie_goal: float,
    protein_goal: float,
    *,
    water_ml: float = 0.0,
    water_goal_ml: float = DEFAULT_WATER_GOAL_ML,
) -> bool:
    return (
        calories > 0
        and calories <= calorie_goal
        and protein >= protein_goal
        and water_ml >= water_goal_ml
    )


def compute_streak_days(
    hit_days: set[str],
    today: datetime.date,
    *,
    grace_miss_days: int = STREAK_GRACE_MISS_DAYS,
    lookback_days: int = STREAK_LOOKBACK_DAYS,
) -> dict[str, Any]:
    """Current streak with a grace window for consecutive misses.

    Up to ``grace_miss_days`` trailing misses keep the prior streak frozen.
    One more consecutive miss resets the streak to 0. Miss days bridged inside
    the grace window do not add to the count but do not break a resumed streak.
    """

    def key(d: datetime.date) -> str:
        return d.strftime("%Y-%m-%d")

    def count_hits_bridging(start: datetime.date) -> int:
        cursor = start
        streak = 0
        miss_run = 0
        for _ in range(lookback_days + 1):
            if key(cursor) in hit_days:
                streak += 1
                miss_run = 0
            else:
                miss_run += 1
                if miss_run > grace_miss_days:
                    break
            cursor -= timedelta(days=1)
        return streak

    trailing_misses = 0
    cursor = today
    while key(cursor) not in hit_days:
        trailing_misses += 1
        if trailing_misses > grace_miss_days:
            ended_start = today - timedelta(days=trailing_misses)
            ended_length = count_hits_bridging(ended_start) if key(ended_start) in hit_days else 0
            just_broke = trailing_misses == grace_miss_days + 1 and ended_length > 0
            return {
                "streak_days": 0,
                "grace_misses": trailing_misses,
                "streak_broken": just_broke,
                "streak_ended_length": ended_length if just_broke else None,
            }
        cursor -= timedelta(days=1)
        if (today - cursor).days > lookback_days:
            return {
                "streak_days": 0,
                "grace_misses": trailing_misses,
                "streak_broken": False,
                "streak_ended_length": None,
            }

    return {
        "streak_days": count_hits_bridging(cursor),
        "grace_misses": trailing_misses,
        "streak_broken": False,
        "streak_ended_length": None,
    }


def normalize_meal_type(value: Optional[str]) -> str:
    text = (value or "").strip().title()
    if text in MEAL_TYPES:
        return text
    lower = text.lower()
    if "break" in lower:
        return "Breakfast"
    if "lunch" in lower:
        return "Lunch"
    if "dinner" in lower or "supper" in lower:
        return "Dinner"
    return "Snack"


class DietService:
    def __init__(self, db: Session):
        self.db = db
        self.settings = get_settings()

    def _user_id(self) -> int:
        return self.settings.default_user_id

    def _get_pref_float(self, key: str, default: float) -> float:
        row = (
            self.db.query(UserPreference)
            .filter(UserPreference.user_id == self._user_id(), UserPreference.key == key)
            .first()
        )
        if not row:
            return default
        try:
            return float(row.value)
        except ValueError:
            return default

    def _set_pref_float(self, key: str, value: float) -> float:
        row = (
            self.db.query(UserPreference)
            .filter(UserPreference.user_id == self._user_id(), UserPreference.key == key)
            .first()
        )
        stored = str(int(value) if value == int(value) else value)
        if row:
            row.value = stored
        else:
            self.db.add(UserPreference(user_id=self._user_id(), key=key, value=stored))
        self.db.flush()
        return float(stored)

    def _get_pref_str(self, key: str, default: str = "") -> str:
        row = (
            self.db.query(UserPreference)
            .filter(UserPreference.user_id == self._user_id(), UserPreference.key == key)
            .first()
        )
        return row.value if row and row.value is not None else default

    def _set_pref_str(self, key: str, value: str) -> str:
        row = (
            self.db.query(UserPreference)
            .filter(UserPreference.user_id == self._user_id(), UserPreference.key == key)
            .first()
        )
        if row:
            row.value = value
        else:
            self.db.add(UserPreference(user_id=self._user_id(), key=key, value=value))
        self.db.flush()
        return value

    def get_goal(self) -> float:
        return self._get_pref_float(GOAL_KEY, DEFAULT_GOAL)

    def get_protein_goal(self) -> float:
        return self._get_pref_float(PROTEIN_GOAL_KEY, DEFAULT_PROTEIN_GOAL)

    def get_water_goal_ml(self) -> float:
        return self._get_pref_float(WATER_GOAL_KEY, DEFAULT_WATER_GOAL_ML)

    def get_water_ml(self, date_str: str) -> float:
        return self._get_pref_float(_water_pref_key(date_str), 0.0)

    def set_water_ml(self, date_str: str, ml: float) -> float:
        return self._set_pref_float(_water_pref_key(date_str), max(0.0, float(ml)))

    def add_water_ml(self, date_str: str, add_ml: float) -> dict[str, Any]:
        date_str = date_str or today_ist()
        total = self.set_water_ml(date_str, self.get_water_ml(date_str) + float(add_ml))
        goal = self.get_water_goal_ml()
        return {
            "date": date_str,
            "water_ml": round(total, 1),
            "water_goal_ml": goal,
            "water_remaining_ml": round(goal - total, 1),
            "hydrated": total >= goal,
        }

    def _water_map(self) -> dict[str, float]:
        rows = (
            self.db.query(UserPreference)
            .filter(
                UserPreference.user_id == self._user_id(),
                UserPreference.key.like("diet_water_ml:%"),
            )
            .all()
        )
        out: dict[str, float] = {}
        for row in rows:
            day = (row.key or "").split(":", 1)[-1]
            if not day:
                continue
            try:
                out[day] = float(row.value)
            except (TypeError, ValueError):
                out[day] = 0.0
        return out

    def set_goal(self, calories: float, protein: Optional[float] = None) -> dict[str, float]:
        cal = self._set_pref_float(GOAL_KEY, calories)
        if protein is not None:
            prot = self._set_pref_float(PROTEIN_GOAL_KEY, protein)
        else:
            prot = self.get_protein_goal()
        return {"calorie_goal": cal, "protein_goal": prot}

    def list_day(self, date_str: Optional[str] = None) -> dict[str, Any]:
        date_str = date_str or today_ist()
        start, end = day_bounds(date_str)
        meals = (
            self.db.query(Meal)
            .filter(
                Meal.user_id == self._user_id(),
                Meal.eaten_at >= start,
                Meal.eaten_at < end,
            )
            .order_by(Meal.eaten_at.asc(), Meal.id.asc())
            .all()
        )
        calories = sum(float(m.calories or 0) for m in meals)
        protein = sum(float(m.protein or 0) for m in meals)
        carbs = sum(float(m.carbs or 0) for m in meals)
        fat = sum(float(m.fat or 0) for m in meals)
        fiber = sum(float(m.fiber or 0) for m in meals)
        goal = self.get_goal()
        protein_goal = self.get_protein_goal()
        water_goal = self.get_water_goal_ml()
        water_ml = self.get_water_ml(date_str)
        return {
            "date": date_str,
            "calorie_goal": goal,
            "protein_goal": protein_goal,
            "water_goal_ml": water_goal,
            "water_ml": round(water_ml, 1),
            "water_remaining_ml": round(water_goal - water_ml, 1),
            "hydrated": water_ml >= water_goal,
            "calories": round(calories, 1),
            "remaining": round(goal - calories, 1),
            "protein": round(protein, 1),
            "protein_remaining": round(protein_goal - protein, 1),
            "carbs": round(carbs, 1),
            "fat": round(fat, 1),
            "fiber": round(fiber, 1),
            "meals": [self.to_out(meal) for meal in meals],
        }

    def list_month(self, month_str: str) -> dict[str, Any]:
        year, month = [int(part) for part in month_str.split("-")]
        start = datetime(year, month, 1, tzinfo=IST).astimezone(timezone.utc)
        if month == 12:
            next_month = datetime(year + 1, 1, 1, tzinfo=IST).astimezone(timezone.utc)
        else:
            next_month = datetime(year, month + 1, 1, tzinfo=IST).astimezone(timezone.utc)
        calorie_goal = self.get_goal()
        protein_goal = self.get_protein_goal()
        water_goal = self.get_water_goal_ml()
        water_by_day = self._water_map()

        # Calendar stars for this month only.
        month_meals = (
            self.db.query(Meal)
            .filter(
                Meal.user_id == self._user_id(),
                Meal.eaten_at >= start,
                Meal.eaten_at < next_month,
            )
            .all()
        )
        month_totals: dict[str, dict[str, float]] = {}
        for meal in month_meals:
            local_day = meal.eaten_at.astimezone(IST).strftime("%Y-%m-%d")
            bucket = month_totals.setdefault(local_day, {"calories": 0.0, "protein": 0.0})
            bucket["calories"] += float(meal.calories or 0)
            bucket["protein"] += float(meal.protein or 0)
        days = []
        for day_key, total in sorted(month_totals.items()):
            days.append(
                {
                    "date": day_key,
                    "hit_goal": day_hit_goal(
                        total["calories"],
                        total["protein"],
                        calorie_goal,
                        protein_goal,
                        water_ml=water_by_day.get(day_key, 0.0),
                        water_goal_ml=water_goal,
                    ),
                }
            )

        # Streak looks further back so month boundaries don't clip it.
        today = datetime.now(IST).date()
        lookback_start = datetime(today.year, today.month, today.day, tzinfo=IST) - timedelta(
            days=STREAK_LOOKBACK_DAYS
        )
        lookback_utc = lookback_start.astimezone(timezone.utc)
        streak_meals = (
            self.db.query(Meal)
            .filter(
                Meal.user_id == self._user_id(),
                Meal.eaten_at >= lookback_utc,
                Meal.eaten_at < datetime.now(timezone.utc) + timedelta(days=1),
            )
            .all()
        )
        streak_totals: dict[str, dict[str, float]] = {}
        for meal in streak_meals:
            local_day = meal.eaten_at.astimezone(IST).strftime("%Y-%m-%d")
            bucket = streak_totals.setdefault(local_day, {"calories": 0.0, "protein": 0.0})
            bucket["calories"] += float(meal.calories or 0)
            bucket["protein"] += float(meal.protein or 0)
        hit_days = {
            day_key
            for day_key, total in streak_totals.items()
            if day_hit_goal(
                total["calories"],
                total["protein"],
                calorie_goal,
                protein_goal,
                water_ml=water_by_day.get(day_key, 0.0),
                water_goal_ml=water_goal,
            )
        }
        streak = compute_streak_days(hit_days, today)
        if streak["streak_broken"] and streak.get("streak_ended_length"):
            self._notify_streak_break(int(streak["streak_ended_length"]), today.strftime("%Y-%m-%d"))

        return {
            "month": month_str,
            "streak_days": streak["streak_days"],
            "grace_misses": streak["grace_misses"],
            "streak_broken": bool(streak["streak_broken"]),
            "streak_ended_length": streak.get("streak_ended_length"),
            "days": days,
        }

    def range_goal_stats(
        self,
        start: datetime,
        end: datetime,
        *,
        label: str,
        period: str,
    ) -> dict[str, Any]:
        calorie_goal = self.get_goal()
        protein_goal = self.get_protein_goal()
        water_goal = self.get_water_goal_ml()
        water_by_day = self._water_map()
        start_utc = start.astimezone(timezone.utc)
        end_utc = end.astimezone(timezone.utc)
        meals = (
            self.db.query(Meal)
            .filter(
                Meal.user_id == self._user_id(),
                Meal.eaten_at >= start_utc,
                Meal.eaten_at <= end_utc,
            )
            .all()
        )
        totals: dict[str, dict[str, float]] = {}
        for meal in meals:
            local_day = meal.eaten_at.astimezone(IST).strftime("%Y-%m-%d")
            bucket = totals.setdefault(local_day, {"calories": 0.0, "protein": 0.0})
            bucket["calories"] += float(meal.calories or 0)
            bucket["protein"] += float(meal.protein or 0)

        today = datetime.now(IST).date()
        first = start.date()
        last = min(end.date(), today)
        hit_dates: list[str] = []
        missed_dates: list[str] = []
        no_log_dates: list[str] = []
        cursor = first
        while cursor <= last:
            key = cursor.strftime("%Y-%m-%d")
            bucket = totals.get(key)
            if bucket is None:
                no_log_dates.append(key)
                missed_dates.append(key)
            elif day_hit_goal(
                bucket["calories"],
                bucket["protein"],
                calorie_goal,
                protein_goal,
                water_ml=water_by_day.get(key, 0.0),
                water_goal_ml=water_goal,
            ):
                hit_dates.append(key)
            else:
                missed_dates.append(key)
            cursor += timedelta(days=1)

        days_in_range = max(0, (last - first).days + 1)
        day_detail = None
        if period == "day":
            day_detail = self.list_day(start.strftime("%Y-%m-%d"))
            day_detail["hit_goal"] = bool(hit_dates)

        hit_count = len(hit_dates)
        missed_count = len(missed_dates)
        insight = self._diet_insight(
            period=period,
            label=label,
            hit_count=hit_count,
            missed_count=missed_count,
            days_in_range=days_in_range,
            no_log_count=len(no_log_dates),
            day_detail=day_detail,
        )
        return {
            "period": period,
            "label": label,
            "calorie_goal": calorie_goal,
            "protein_goal": protein_goal,
            "days_in_range": days_in_range,
            "hit_days": hit_count,
            "missed_days": missed_count,
            "logged_days": days_in_range - len(no_log_dates),
            "no_log_days": len(no_log_dates),
            "hit_dates": hit_dates,
            "missed_dates": missed_dates,
            "no_log_dates": no_log_dates,
            "day": day_detail,
            "insight": insight,
        }

    @staticmethod
    def _diet_insight(
        *,
        period: str,
        label: str,
        hit_count: int,
        missed_count: int,
        days_in_range: int,
        no_log_count: int,
        day_detail: Optional[dict[str, Any]],
    ) -> str:
        if period == "day" and day_detail:
            hit = bool(day_detail.get("hit_goal"))
            cal = day_detail.get("calories")
            prot = day_detail.get("protein")
            cal_g = day_detail.get("calorie_goal")
            prot_g = day_detail.get("protein_goal")
            if hit:
                return (
                    f"On {label} you hit your target — {cal} kcal "
                    f"(goal {cal_g}) and {prot} g protein (goal {prot_g})."
                )
            if not day_detail.get("meals"):
                return f"On {label} you did not meet your target — no meals were logged."
            return (
                f"On {label} you did not meet your target. "
                f"You logged {cal} kcal (goal {cal_g}) and {prot} g protein (goal {prot_g})."
            )
        if days_in_range <= 0:
            return f"No diet days in {label} yet."
        extra = ""
        if no_log_count:
            extra = f" {no_log_count} of the miss days had no meals logged."
        return (
            f"In {label} you hit your calorie and protein target on {hit_count} of "
            f"{days_in_range} days, and did not meet it on {missed_count} days.{extra}"
        )

    def period_goal_stats(
        self,
        period: str = "month",
        *,
        date: Optional[str] = None,
        year: Optional[int] = None,
        month: Optional[int] = None,
    ) -> dict[str, Any]:
        from app.services.analytics_service import AnalyticsService

        window = AnalyticsService(self.db).resolve_window(
            period, date=date, year=year, month=month
        )
        return self.range_goal_stats(
            window["start"],
            window["end"],
            label=window["label"],
            period=window["period"],
        )

    def _notify_streak_break(self, ended_length: int, on_date: str) -> None:
        if ended_length <= 0:
            return
        if self._get_pref_str(STREAK_BREAK_NOTIFIED_KEY) == on_date:
            return
        self._set_pref_str(STREAK_BREAK_NOTIFIED_KEY, on_date)
        self.db.commit()
        title = "Streak ended 😢"
        body = f"Your {ended_length}-day diet streak has come to an end. Starting fresh."
        try:
            from app.services.push_service import PushService

            PushService(self.db).notify_payment(
                title=title,
                body=body,
                user_id=self._user_id(),
                url="/diet",
            )
        except Exception as extra:  # noqa: BLE001
            logger.warning("Streak break push failed: %s", extra)

    def create(self, payload: MealCreate, source: str = "manual") -> Meal:
        eaten = payload.eaten_at or datetime.now(timezone.utc)
        if eaten.tzinfo is None:
            eaten = eaten.replace(tzinfo=timezone.utc)
        meal = Meal(
            user_id=self._user_id(),
            name=payload.name.strip(),
            meal_type=normalize_meal_type(payload.meal_type),
            calories=float(payload.calories),
            protein=payload.protein,
            carbs=payload.carbs,
            fat=payload.fat,
            fiber=payload.fiber,
            notes=payload.notes,
            source=source,
            eaten_at=eaten,
        )
        self.db.add(meal)
        self.db.flush()
        self._remember_meal(meal)
        return meal

    def update(self, meal_id: int, payload: MealUpdate) -> Optional[Meal]:
        meal = self.db.get(Meal, meal_id)
        if not meal or meal.user_id != self._user_id():
            return None
        data = payload.model_dump(exclude_unset=True)
        if "meal_type" in data and data["meal_type"]:
            data["meal_type"] = normalize_meal_type(data["meal_type"])
        if "name" in data and data["name"]:
            data["name"] = data["name"].strip()
        for key, value in data.items():
            setattr(meal, key, value)
        self.db.flush()
        self._remember_meal(meal)
        return meal

    def delete(self, meal_id: int) -> bool:
        meal = self.db.get(Meal, meal_id)
        if not meal or meal.user_id != self._user_id():
            return False
        self.db.delete(meal)
        self.db.flush()
        return True

    def create_from_nl(self, payload: MealNL) -> tuple[Meal, str]:
        parsed = self._parse_nl(payload.text)
        create = MealCreate(
            name=parsed["name"],
            meal_type=normalize_meal_type(parsed.get("meal_type")),
            calories=float(parsed.get("calories") or 0),
            protein=parsed.get("protein"),
            carbs=parsed.get("carbs"),
            fat=parsed.get("fat"),
            fiber=parsed.get("fiber"),
            eaten_at=payload.eaten_at,
        )
        meal = self.create(create, source="nl")
        reply = f"Logged {meal.name} · {meal.meal_type} · {int(meal.calories)} kcal"
        return meal, reply

    def _parse_nl(self, text: str) -> dict[str, Any]:
        if self.settings.openai_api_key:
            try:
                client = OpenAI(api_key=self.settings.openai_api_key)
                response = client.chat.completions.create(
                    model=self.settings.openai_model,
                    temperature=0,
                    response_format={"type": "json_object"},
                    messages=[
                        {"role": "system", "content": NL_SYSTEM},
                        {"role": "user", "content": text},
                    ],
                )
                data = json.loads(response.choices[0].message.content or "{}")
                if data.get("name"):
                    return data
            except Exception as extra:  # noqa: BLE001
                logger.warning("Diet NL parse failed: %s", extra)
        return self._heuristic_nl(text)

    def estimate(self, food: str) -> MealEstimateOut:
        data, source = self._estimate_food(food)
        return MealEstimateOut(
            name=str(data.get("name") or food).strip()[:255],
            calories=round(float(data.get("calories") or 0), 0),
            protein=round(float(data.get("protein") or 0), 1),
            carbs=round(float(data.get("carbs") or 0), 1),
            fat=round(float(data.get("fat") or 0), 1),
            fiber=round(float(data.get("fiber") or 0), 1),
            source=source,
        )

    def _lookup_memory(self, food: str) -> dict[str, Any] | None:
        key = _memory_key(food)
        if not key:
            return None
        memory = (
            self.db.query(MealMemory)
            .filter(MealMemory.user_id == self._user_id(), MealMemory.meal_key == key)
            .first()
        )
        if memory:
            return {
                "name": memory.meal_display,
                "calories": float(memory.calories),
                "protein": float(memory.protein or 0),
                "carbs": float(memory.carbs or 0),
                "fat": float(memory.fat or 0),
                "fiber": float(memory.fiber or 0),
            }
        # Fuzzy: match when only quantity words differ (one scoop vs on scoop).
        stripped = re.sub(r"(scoop|scoops|bowl|piece|pieces|cup|cups|gram|grams)", "", key)
        if len(stripped) >= 4:
            candidates = (
                self.db.query(MealMemory)
                .filter(MealMemory.user_id == self._user_id())
                .order_by(MealMemory.hit_count.desc(), MealMemory.updated_at.desc())
                .limit(50)
                .all()
            )
            for row in candidates:
                row_stripped = re.sub(r"(scoop|scoops|bowl|piece|pieces|cup|cups|gram|grams)", "", row.meal_key)
                if stripped == row_stripped or stripped in row_stripped or row_stripped in stripped:
                    return {
                        "name": row.meal_display,
                        "calories": float(row.calories),
                        "protein": float(row.protein or 0),
                        "carbs": float(row.carbs or 0),
                        "fat": float(row.fat or 0),
                        "fiber": float(row.fiber or 0),
                    }
        return None

    def _remember_meal(self, meal: Meal) -> None:
        key = _memory_key(meal.name)
        if not key:
            return
        memory = (
            self.db.query(MealMemory)
            .filter(MealMemory.user_id == self._user_id(), MealMemory.meal_key == key)
            .first()
        )
        if memory:
            memory.meal_display = meal.name
            memory.calories = float(meal.calories)
            memory.protein = meal.protein
            memory.carbs = meal.carbs
            memory.fat = meal.fat
            memory.fiber = meal.fiber
            memory.hit_count = (memory.hit_count or 0) + 1
        else:
            self.db.add(
                MealMemory(
                    user_id=self._user_id(),
                    meal_key=key,
                    meal_display=meal.name,
                    calories=float(meal.calories),
                    protein=meal.protein,
                    carbs=meal.carbs,
                    fat=meal.fat,
                    fiber=meal.fiber,
                    hit_count=1,
                )
            )
        self.db.flush()

    def _estimate_food(self, food: str) -> tuple[dict[str, Any], str]:
        text = (food or "").strip()
        remembered = self._lookup_memory(text)
        if remembered:
            return remembered, "memory"
        branded = _branded_estimate(text)
        if branded:
            return branded, "branded"
        if self.settings.openai_api_key:
            try:
                client = OpenAI(api_key=self.settings.openai_api_key)
                response = client.chat.completions.create(
                    model=self.settings.openai_chat_model or self.settings.openai_model,
                    temperature=0,
                    response_format={"type": "json_object"},
                    messages=[
                        {"role": "system", "content": ESTIMATE_SYSTEM},
                        {"role": "user", "content": text},
                    ],
                )
                data = json.loads(response.choices[0].message.content or "{}")
                if data.get("calories") is not None:
                    data["name"] = data.get("name") or text
                    return data, "ai"
            except Exception as extra:  # noqa: BLE001
                logger.warning("Diet estimate failed: %s", extra)
        return self._heuristic_estimate(text), "heuristic"

    @staticmethod
    def _heuristic_estimate(text: str) -> dict[str, Any]:
        _WORD_NUMS = {
            "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
            "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
        }
        raw = (text or "").strip()
        lower = raw.lower()
        multiplier = 1.0
        if re.search(r"\b(half|1/2|½)\b", lower):
            multiplier = 0.5
        else:
            grams = re.search(r"(\d+(?:\.\d+)?)\s*g\b", lower)
            if grams:
                multiplier = float(grams.group(1)) / 100.0
            else:
                count = re.search(r"\b(\d+(?:\.\d+)?)\b", lower)
                if count:
                    multiplier = float(count.group(1))
                else:
                    for word, num in _WORD_NUMS.items():
                        if re.search(rf"\b{word}\b", lower):
                            multiplier = float(num)
                            break
        base = (180.0, 6.0, 20.0, 7.0, 3.0)
        for keys, macros in _FOOD_HINTS:
            if any(key in lower for key in keys):
                base = macros
                break
        calories, protein, carbs, fat, fiber = (value * multiplier for value in base)
        return {
            "name": raw[:255] or "Meal",
            "calories": calories,
            "protein": protein,
            "carbs": carbs,
            "fat": fat,
            "fiber": fiber,
        }

    @staticmethod
    def _heuristic_nl(text: str) -> dict[str, Any]:
        raw = (text or "").strip()
        lower = raw.lower()
        meal_type = "Snack"
        for label in MEAL_TYPES:
            if label.lower() in lower:
                meal_type = label
                break
        calories = 0.0
        cal_match = re.search(r"(\d{2,4})\s*(?:k?cal|calories)?", lower)
        if cal_match:
            calories = float(cal_match.group(1))
        name = re.sub(r"\b(for|at)?\s*(breakfast|lunch|dinner|snack)\b", "", raw, flags=re.I)
        name = re.sub(r"\d{2,4}\s*(k?cal|calories)?", "", name, flags=re.I)
        name = re.sub(r"\s+", " ", name).strip(" -.,") or "Meal"
        return {
            "name": name[:255],
            "meal_type": meal_type,
            "calories": calories,
            "protein": None,
            "carbs": None,
            "fat": None,
            "fiber": None,
        }

    @staticmethod
    def to_out(meal: Meal) -> MealOut:
        return MealOut.model_validate(meal)
