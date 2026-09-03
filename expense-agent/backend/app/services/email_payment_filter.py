"""Helpers to decide if a Gmail message is a real payment alert."""

from __future__ import annotations

import re

from app.services.bank_email_parser import is_money_movement_email

PAYMENT_HINTS = re.compile(
    r"("
    r"debited|credited|spent|paid to|payment of|txn|transaction alert|"
    r"upi ref|upi-|imps|neft|purchase on|card ending|credit card|"
    r"info:|rs\.?\s*[0-9]|inr\s*[0-9]|₹\s*[0-9]"
    r")",
    re.I,
)

NOISE_HINTS = re.compile(
    r"("
    r"digest|newsletter|unsubscribe|job alert|hiring|lpa\b|"
    r"welcome to|policy copy|funds/securities balance|"
    r"did you know|banking = 2 taps|groww digest|"
    r"statement for the period|"
    r"declined|rejected|failed|unsuccessful|otp\b|one[\s-]?time password"
    r")",
    re.I,
)

MERCHANT_EXTRA = [
    re.compile(
        r"(?:Info|INFO):\s*(?:INR|Rs\.?|₹)?\s*[0-9,.]+\s+spent on\s+([A-Za-z0-9][A-Za-z0-9 &.@'_-]{1,80})",
        re.I,
    ),
    re.compile(
        r"(?:spent on|purchased at|purchase at|at)\s+([A-Za-z0-9][A-Za-z0-9 &.@'_-]{1,60})",
        re.I,
    ),
    re.compile(
        r"(?:towards|for)\s+([A-Za-z0-9][A-Za-z0-9 &.@'_-]{1,60})\s+(?:on your|via)",
        re.I,
    ),
]


def is_likely_payment_email(subject: str, body: str) -> bool:
    blob = f"{subject}\n{body}"
    if NOISE_HINTS.search(subject or ""):
        return False
    # Declined / rejected / OTP-only mails never count as payments
    if not is_money_movement_email(subject, body):
        return False
    if NOISE_HINTS.search(blob) and not PAYMENT_HINTS.search(blob):
        return False
    return bool(PAYMENT_HINTS.search(blob))


def extract_merchant_from_email(text: str) -> str | None:
    from app.services.bank_email_parser import strip_credit_limit_suffix

    for pattern in MERCHANT_EXTRA:
        match = pattern.search(text)
        if match:
            value = match.group(1).strip(" .,-")
            value = re.sub(r"\s+via\s+.*$", "", value, flags=re.I)
            value = re.sub(r"\s+on\s+\d{1,2}.*$", "", value, flags=re.I)
            value = strip_credit_limit_suffix(value)
            if value.lower() in {
                "the primary card holder",
                "your icici bank credit card",
                "credit card",
            }:
                continue
            if not value:
                continue
            return value[:255]
    return None
