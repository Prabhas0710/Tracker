"""Daily chat briefing: greeting, festivals, and yesterday recap."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Optional
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import ChatMessage, Expense, User, UserPreference
from app.services.diet_service import DietService, day_bounds, today_ist

IST = ZoneInfo("Asia/Kolkata")
BRIEFING_KEY = "chat_briefing_date"
DISPLAY_NAME_KEY = "display_name"

# Major Indian festivals — fixed calendar dates (YYYY-MM-DD) for 2026.
FESTIVALS_2026: dict[str, str] = {
    "2026-01-01": "New Year",
    "2026-01-14": "Makar Sankranti",
    "2026-01-26": "Republic Day",
    "2026-03-03": "Holi",
    "2026-03-30": "Ugadi",
    "2026-04-14": "Tamil New Year / Vishu",
    "2026-08-15": "Independence Day",
    "2026-08-28": "Raksha Bandhan",
    "2026-09-04": "Janmashtami",
    "2026-09-14": "Ganesh Chaturthi",
    "2026-10-02": "Gandhi Jayanti",
    "2026-10-20": "Dussehra",
    "2026-11-08": "Diwali",
    "2026-11-09": "Diwali",
    "2026-12-25": "Christmas",
}

FIXED_MM_DD: dict[str, str] = {
    "01-26": "Republic Day",
    "08-15": "Independence Day",
    "10-02": "Gandhi Jayanti",
    "12-25": "Christmas",
}


def shift_date(date_str: str, days: int) -> str:
    year, month, day = [int(part) for part in date_str.split("-")]
    shifted = datetime(year, month, day, tzinfo=IST) + timedelta(days=days)
    return shifted.strftime("%Y-%m-%d")


def pretty_day(date_str: str) -> str:
    year, month, day = [int(part) for part in date_str.split("-")]
    dt = datetime(year, month, day, tzinfo=IST)
    return f"{dt.strftime('%a')}, {day} {dt.strftime('%b')}"


class BriefingService:
    def __init__(self, db: Session):
        self.db = db
        self.settings = get_settings()

    def _user_id(self) -> int:
        return self.settings.default_user_id

    def display_name(self) -> str:
        pref = (
            self.db.query(UserPreference)
            .filter(UserPreference.user_id == self._user_id(), UserPreference.key == DISPLAY_NAME_KEY)
            .first()
        )
        if pref and pref.value.strip():
            return pref.value.strip()
        user = self.db.get(User, self._user_id())
        if user and user.name and user.name.strip() and user.name != "Default User":
            return user.name.split()[0]
        return "Prabhas"

    def festival_today(self, date_str: Optional[str] = None) -> Optional[str]:
        date_str = date_str or today_ist()
        if date_str in FESTIVALS_2026:
            return FESTIVALS_2026[date_str]
        mm_dd = date_str[5:]
        return FIXED_MM_DD.get(mm_dd)

    def _already_briefed_today(self) -> bool:
        row = (
            self.db.query(UserPreference)
            .filter(UserPreference.user_id == self._user_id(), UserPreference.key == BRIEFING_KEY)
            .first()
        )
        return bool(row and row.value == today_ist())

    def _mark_briefed(self) -> None:
        today = today_ist()
        row = (
            self.db.query(UserPreference)
            .filter(UserPreference.user_id == self._user_id(), UserPreference.key == BRIEFING_KEY)
            .first()
        )
        if row:
            row.value = today
        else:
            self.db.add(UserPreference(user_id=self._user_id(), key=BRIEFING_KEY, value=today))
        self.db.flush()

    def _day_spend(self, date_str: str) -> tuple[float, int]:
        start, end = day_bounds(date_str)
        rows = (
            self.db.query(Expense)
            .filter(
                Expense.user_id == self._user_id(),
                Expense.spent_at >= start,
                Expense.spent_at < end,
                Expense.direction == "debit",
            )
            .all()
        )
        total = sum(float(row.amount or 0) for row in rows)
        return total, len(rows)

    def _spend_verdict(self, yesterday: float, prior: float) -> str:
        if yesterday == 0 and prior == 0:
            return "No spend was logged yesterday."
        if yesterday == 0:
            return f"No spend logged yesterday (day before was ₹{prior:,.0f})."
        if prior == 0:
            return f"You spent ₹{yesterday:,.0f} yesterday — first logged day in this stretch."
        delta = yesterday - prior
        pct = abs(delta) / prior * 100 if prior else 0
        if delta <= -prior * 0.1:
            return f"₹{yesterday:,.0f} yesterday — about {pct:.0f}% lower than the day before (₹{prior:,.0f}). Nice control."
        if delta >= prior * 0.1:
            return f"₹{yesterday:,.0f} yesterday — about {pct:.0f}% higher than the day before (₹{prior:,.0f})."
        return f"₹{yesterday:,.0f} yesterday — about the same as the day before (₹{prior:,.0f})."

    def _diet_recap(self, date_str: str) -> str:
        day = DietService(self.db).list_day(date_str)
        meals = day["meals"]
        if not meals:
            return (
                f"No meals logged on {pretty_day(date_str)}. "
                f"Goals are {int(day['calorie_goal'])} kcal and {int(day['protein_goal'])} g protein."
            )
        hit_cal = day["calories"] <= day["calorie_goal"]
        hit_prot = day["protein"] >= day["protein_goal"]
        if hit_cal and hit_prot:
            goal_note = "You hit both calorie and protein goals."
        elif hit_cal:
            goal_note = "Calories were on target; protein was a little short."
        elif hit_prot:
            goal_note = "Protein was on target; calories ran a bit high."
        else:
            goal_note = "Both goals were missed — room to tighten today."
        return (
            f"Diet ({pretty_day(date_str)}): {int(day['calories'])} kcal "
            f"(goal {int(day['calorie_goal'])}) · {int(day['protein'])} g protein "
            f"(goal {int(day['protein_goal'])}). {goal_note}"
        )

    def build_message(self) -> str:
        name = self.display_name()
        today = today_ist()
        yesterday = shift_date(today, -1)
        prior = shift_date(today, -2)

        lines = [f"Welcome back, {name}."]
        festival = self.festival_today(today)
        if festival:
            lines.append(f"Happy {festival}! Hope you're having a good one.")

        y_spend, y_count = self._day_spend(yesterday)
        p_spend, _ = self._day_spend(prior)
        spend_line = self._spend_verdict(y_spend, p_spend)
        if y_count:
            spend_line = f"{spend_line} ({y_count} payment{'s' if y_count != 1 else ''})."

        lines.append("")
        lines.append(f"Yesterday at a glance ({pretty_day(yesterday)}):")
        lines.append(f"• Spend: {spend_line}")
        lines.append(f"• {self._diet_recap(yesterday)}")
        lines.append("")
        lines.append("Ask me anything — I'll look things up or make changes for you.")
        return "\n".join(lines)

    def ensure_daily_briefing(self) -> Optional[str]:
        if self._already_briefed_today():
            return None
        text = self.build_message()
        self.db.add(ChatMessage(user_id=self._user_id(), role="assistant", content=text))
        self._mark_briefed()
        self.db.commit()
        return text
