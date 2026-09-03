"""Craft clarification and confirmation messages for the user."""

from __future__ import annotations

from typing import Optional


class NotificationAgent:
    def should_ask(self, confidence: float, threshold: float) -> bool:
        return confidence < threshold

    def clarification_prompt(
        self,
        *,
        amount: float,
        merchant: Optional[str],
    ) -> str:
        merchant_line = f"Merchant: {merchant}\n\n" if merchant else ""
        return (
            f"₹{amount:,.2f} payment detected.\n\n"
            f"{merchant_line}"
            "Waiting for a category — Food, Entertainment, Personal, or type your own."
        )

    def confirmation_prompt(
        self,
        *,
        amount: float,
        category: str,
        subcategory: Optional[str],
        description: Optional[str],
        merchant: Optional[str] = None,
    ) -> str:
        sub = f" → {subcategory}" if subcategory else ""
        desc = f"\n{description}" if description else ""
        merch = f"\n{merchant}" if merchant else ""
        return (
            f"₹{amount:,.2f}\n"
            f"{category}{sub}"
            f"{merch}"
            f"{desc}\n\n"
            "Confirm or edit?"
        )

    def saved_message(
        self,
        *,
        amount: float,
        category: str,
        subcategory: Optional[str],
        merchant: Optional[str],
    ) -> str:
        sub = f" → {subcategory}" if subcategory else ""
        merch = f"\n{merchant}" if merchant else ""
        return f"Expense saved.\n\n₹{amount:,.2f}\n{category}{sub}{merch}"
