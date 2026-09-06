"""SQL aggregates for dashboard and analytics — source of financial truth."""

from __future__ import annotations

from calendar import monthrange
from datetime import datetime, timedelta
from typing import Any, Optional
from zoneinfo import ZoneInfo

from sqlalchemy import case, func
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import Expense, Transaction
from app.services.credit_card_cycle_service import (
    CardBank,
    CreditCardCycleService,
    SUPPORTED_BANKS,
    classify_cc_spend_in_month,
    infer_card_issuer_from_transaction,
)

IST = ZoneInfo("Asia/Kolkata")


class AnalyticsService:
    def __init__(self, db: Session):
        self.db = db
        self.settings = get_settings()

    @staticmethod
    def _month_bounds(year: int, month: int) -> tuple[datetime, datetime]:
        """Inclusive month window in IST — matches the dashboard month picker."""
        start = datetime(year, month, 1, tzinfo=IST)
        last_day = monthrange(year, month)[1]
        end = datetime(year, month, last_day, 23, 59, 59, tzinfo=IST)
        return start, end

    def _cc_bank_totals(
        self,
        user_id: int,
        start: datetime,
        end: datetime,
        cycle_svc: CreditCardCycleService,
    ) -> tuple[dict[str, dict[str, Any]], float, float]:
        """Per-bank cycle vs due totals for credit card spends."""
        rows = (
            self.db.query(Expense, Transaction)
            .join(Transaction, Transaction.id == Expense.transaction_id)
            .filter(
                Expense.user_id == user_id,
                Expense.spent_at >= start,
                Expense.spent_at <= end,
                Expense.direction == "debit",
                Transaction.payment_method == "Credit Card",
            )
            .all()
        )

        bank_stats: dict[str, dict[str, Any]] = {
            bank: {
                **cycle_svc.get_bank_cycle_info(bank, user_id=user_id),
                "cycle_spent": 0.0,
                "unbilled_amount": 0.0,
                "due_amount": 0.0,
            }
            for bank in SUPPORTED_BANKS
        }
        cycle_spent_total = 0.0
        due_total = 0.0

        for expense, txn in rows:
            bank = infer_card_issuer_from_transaction(txn)
            if not bank:
                continue
            cycle_start = cycle_svc.get_cycle_start(bank, user_id=user_id)
            bucket = classify_cc_spend_in_month(
                expense.spent_at, start, end, cycle_start, bank=bank
            )
            amount = float(expense.amount)
            if bucket == "bill":
                bank_stats[bank]["cycle_spent"] += amount
                cycle_spent_total += amount
            elif bucket == "current":
                bank_stats[bank]["unbilled_amount"] += amount
            else:
                bank_stats[bank]["due_amount"] += amount
                due_total += amount

        return bank_stats, cycle_spent_total, due_total

    @staticmethod
    def _inr(amount: float) -> str:
        return f"{amount:,.2f} INR"

    def resolve_window(
        self,
        period: str = "month",
        *,
        date: Optional[str] = None,
        year: Optional[int] = None,
        month: Optional[int] = None,
    ) -> dict[str, Any]:
        now = datetime.now(IST)
        period = (period or "month").lower()
        if period not in {"day", "week", "month", "year"}:
            period = "month"

        if period == "day":
            stamp = date or now.strftime("%Y-%m-%d")
            y, m, d = [int(part) for part in stamp.split("-")]
            start = datetime(y, m, d, tzinfo=IST)
            end = datetime(y, m, d, 23, 59, 59, tzinfo=IST)
            return {
                "period": "day",
                "start": start,
                "end": end,
                "label": start.strftime("%d %B %Y"),
                "year": y,
                "month": m,
                "date": stamp,
            }

        if period == "week":
            stamp = date or now.strftime("%Y-%m-%d")
            y, m, d = [int(part) for part in stamp.split("-")]
            day = datetime(y, m, d, tzinfo=IST).date()
            monday = day - timedelta(days=day.weekday())
            sunday = monday + timedelta(days=6)
            start = datetime(monday.year, monday.month, monday.day, tzinfo=IST)
            end = datetime(sunday.year, sunday.month, sunday.day, 23, 59, 59, tzinfo=IST)
            return {
                "period": "week",
                "start": start,
                "end": end,
                "label": f"{monday.strftime('%d %b')} – {sunday.strftime('%d %b %Y')}",
                "year": monday.year,
                "month": monday.month,
                "date": monday.strftime("%Y-%m-%d"),
            }

        if period == "year":
            y = year or now.year
            start = datetime(y, 1, 1, tzinfo=IST)
            end = datetime(y, 12, 31, 23, 59, 59, tzinfo=IST)
            return {
                "period": "year",
                "start": start,
                "end": end,
                "label": str(y),
                "year": y,
                "month": 1,
                "date": f"{y}-01-01",
            }

        y = year or now.year
        m = month or now.month
        start, end = self._month_bounds(y, m)
        return {
            "period": "month",
            "start": start,
            "end": end,
            "label": start.strftime("%B %Y"),
            "year": y,
            "month": m,
            "date": f"{y}-{m:02d}-01",
        }

    def expense_insight(self, summary: dict[str, Any]) -> str:
        total = float(summary.get("total_spent") or 0)
        label = summary.get("label") or "this period"
        period = summary.get("period") or "month"
        cats = summary.get("by_category") or []
        top = cats[0] if cats else None
        top_name = (top or {}).get("category")
        top_amount = float((top or {}).get("amount") or 0)

        if total <= 0:
            return f"No spending recorded for {label}."
        if period == "day":
            if top:
                return (
                    f"On {label} you spent {self._inr(total)} in total. "
                    f"Most of it went to {top_name} ({self._inr(top_amount)})."
                )
            return f"On {label} you spent {self._inr(total)}."
        if period == "week":
            if top:
                return (
                    f"In the week of {label} you spent {self._inr(total)} in total. "
                    f"You spent the most on {top_name} ({self._inr(top_amount)})."
                )
            return f"In the week of {label} you spent {self._inr(total)}."
        if period == "year":
            if top:
                return (
                    f"In {label} you spent {self._inr(total)} in total. "
                    f"The highest category was {top_name} ({self._inr(top_amount)})."
                )
            return f"In {label} you spent {self._inr(total)}."
        if top:
            return (
                f"In {label} you spent {self._inr(total)} in total, "
                f"with the most going to {top_name} ({self._inr(top_amount)})."
            )
        return f"In {label} you spent {self._inr(total)}."

    def range_summary(
        self,
        start: datetime,
        end: datetime,
        *,
        label: str,
        period: str,
        year: int,
        month: int,
        date: Optional[str] = None,
        user_id: Optional[int] = None,
    ) -> dict[str, Any]:
        user_id = user_id or self.settings.default_user_id
        cycle_svc = CreditCardCycleService(self.db)

        totals = (
            self.db.query(
                func.coalesce(
                    func.sum(case((Expense.direction == "debit", Expense.amount), else_=0)),
                    0,
                ),
                func.coalesce(
                    func.sum(case((Expense.direction == "credit", Expense.amount), else_=0)),
                    0,
                ),
                func.coalesce(
                    func.sum(case((Expense.direction == "transfer", Expense.amount), else_=0)),
                    0,
                ),
            )
            .filter(
                Expense.user_id == user_id,
                Expense.spent_at >= start,
                Expense.spent_at <= end,
            )
            .one()
        )
        total_debits = float(totals[0] or 0)
        total_credits = float(totals[1] or 0)
        total_transfers = float(totals[2] or 0)
        net = total_debits - total_credits

        rows = (
            self.db.query(Expense.category, func.coalesce(func.sum(Expense.amount), 0))
            .filter(
                Expense.user_id == user_id,
                Expense.spent_at >= start,
                Expense.spent_at <= end,
                Expense.direction == "debit",
            )
            .group_by(Expense.category)
            .order_by(func.sum(Expense.amount).desc())
            .all()
        )
        by_category = [
            {"category": category, "amount": float(amount)} for category, amount in rows
        ]

        bank_stats, credit_card_spent, credit_card_due = self._cc_bank_totals(
            user_id, start, end, cycle_svc
        )

        credit_rows = (
            self.db.query(Expense.category, func.coalesce(func.sum(Expense.amount), 0))
            .filter(
                Expense.user_id == user_id,
                Expense.spent_at >= start,
                Expense.spent_at <= end,
                Expense.direction == "credit",
            )
            .group_by(Expense.category)
            .order_by(func.sum(Expense.amount).desc())
            .all()
        )
        by_credit_category = [
            {"category": category, "amount": float(amount)} for category, amount in credit_rows
        ]

        cycle = cycle_svc.get_all_cycles(user_id=user_id)
        top = by_category[0] if by_category else None

        payload = {
            "period": period,
            "year": year,
            "month": month,
            "date": date,
            "label": label,
            "start": start.isoformat(),
            "end": end.isoformat(),
            "total_spent": total_debits,
            "total_debits": total_debits,
            "total_credits": total_credits,
            "total_transfers": total_transfers,
            "net": net,
            "by_category": by_category,
            "by_credit_category": by_credit_category,
            "top_category": top["category"] if top else None,
            "top_category_amount": float(top["amount"]) if top else 0.0,
            "credit_card_spent": credit_card_spent,
            "credit_card_due": credit_card_due,
            "credit_card_banks": bank_stats,
            "credit_card_cycle": cycle,
            "currency": "INR",
        }
        payload["insight"] = self.expense_insight(payload)
        return payload

    def period_summary(
        self,
        period: str = "month",
        *,
        date: Optional[str] = None,
        year: Optional[int] = None,
        month: Optional[int] = None,
        user_id: Optional[int] = None,
    ) -> dict[str, Any]:
        window = self.resolve_window(period, date=date, year=year, month=month)
        return self.range_summary(
            window["start"],
            window["end"],
            label=window["label"],
            period=window["period"],
            year=window["year"],
            month=window["month"],
            date=window.get("date"),
            user_id=user_id,
        )

    def monthly_summary(
        self, year: int, month: int, user_id: Optional[int] = None
    ) -> dict[str, Any]:
        return self.period_summary("month", year=year, month=month, user_id=user_id)

    def current_month_summary(self, user_id: Optional[int] = None) -> dict[str, Any]:
        now = datetime.now(IST)
        return self.monthly_summary(now.year, now.month, user_id=user_id)
