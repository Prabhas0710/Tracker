"""Parse raw UPI / bank SMS payment text into structured fields."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Optional

AMOUNT_PATTERNS = [
    re.compile(r"(?:₹|INR|Rs\.?)\s*([0-9]{1,3}(?:,[0-9]{2,3})*(?:\.[0-9]{1,2})?|[0-9]+(?:\.[0-9]{1,2})?)", re.I),
    re.compile(r"([0-9]{1,3}(?:,[0-9]{2,3})*(?:\.[0-9]{1,2})?|[0-9]+(?:\.[0-9]{1,2})?)\s*(?:paid|debited)", re.I),
]

MERCHANT_PATTERNS = [
    re.compile(r"(?:paid to|to:|to)\s+([A-Za-z0-9][A-Za-z0-9 &.@'_-]{1,80})", re.I),
    re.compile(r"UPI(?:\s+payment)?\s+of\s+(?:₹|INR|Rs\.?)?\s*[0-9,.]+\s+to\s+([^\s]+)", re.I),
]

UPI_REF_PATTERNS = [
    re.compile(r"(?:UPI\s*Ref(?:erence)?(?:\s*No\.?)?[:\s]+)([A-Za-z0-9]+)", re.I),
    re.compile(r"(?:Ref(?:erence)?(?:\s*No\.?)?[:\s]+)([0-9]{6,})", re.I),
    re.compile(r"(?:TXN|Txn)[:\s#-]*([A-Za-z0-9]+)", re.I),
]

ACCOUNT_PATTERNS = [
    re.compile(r"A/?c\s*(?:XX|X*|)\s*([0-9]{3,6})", re.I),
]

VPA_PATTERN = re.compile(r"\b([a-zA-Z0-9._-]+@[a-zA-Z]+)\b")


def _parse_amount(text: str) -> Optional[float]:
    for pattern in AMOUNT_PATTERNS:
        match = pattern.search(text)
        if match:
            raw = match.group(1).replace(",", "")
            try:
                return float(raw)
            except ValueError:
                continue
    return None


def _clean_merchant(value: str) -> str:
    cleaned = value.strip(" .,-")
    cleaned = re.sub(r"\s+via\s+UPI.*$", "", cleaned, flags=re.I)
    cleaned = re.sub(r"\s+on\s+\d{1,2}[-/].*$", "", cleaned, flags=re.I)
    return cleaned.strip()[:255]


def _parse_merchant(text: str) -> Optional[str]:
    for pattern in MERCHANT_PATTERNS:
        match = pattern.search(text)
        if match:
            return _clean_merchant(match.group(1))
    vpa = VPA_PATTERN.search(text)
    if vpa:
        return vpa.group(1)
    return None


def _parse_upi_ref(text: str) -> Optional[str]:
    for pattern in UPI_REF_PATTERNS:
        match = pattern.search(text)
        if match:
            return match.group(1)
    return None


def _parse_account_suffix(text: str) -> Optional[str]:
    match = ACCOUNT_PATTERNS[0].search(text)
    return match.group(1) if match else None


def normalize_merchant_key(merchant: Optional[str]) -> Optional[str]:
    if not merchant:
        return None
    key = merchant.lower().strip()
    key = re.sub(r"[^a-z0-9@._\s-]", "", key)
    key = re.sub(r"\s+", " ", key)
    return key


def parse_payment_text(
    raw_text: str,
    *,
    amount: Optional[float] = None,
    merchant: Optional[str] = None,
    transaction_id: Optional[str] = None,
    upi_ref: Optional[str] = None,
    account_suffix: Optional[str] = None,
    payment_method: Optional[str] = None,
    timestamp: Optional[datetime] = None,
    source: str = "manual",
) -> dict:
    text = (raw_text or "").strip()
    parsed_amount = amount if amount is not None else _parse_amount(text)
    if parsed_amount is None:
        raise ValueError("Could not determine payment amount from event")

    parsed_merchant = merchant or _parse_merchant(text)
    parsed_upi = upi_ref or transaction_id or _parse_upi_ref(text)
    parsed_txn = transaction_id or parsed_upi
    parsed_account = account_suffix or _parse_account_suffix(text)
    method = payment_method or ("UPI" if "upi" in text.lower() else "Unknown")
    ts = timestamp or datetime.now(timezone.utc)
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)

    return {
        "source": source,
        "amount": float(parsed_amount),
        "merchant": parsed_merchant,
        "payment_method": method,
        "transaction_id": parsed_txn,
        "upi_ref": parsed_upi,
        "account_suffix": parsed_account,
        "timestamp": ts,
        "raw_text": text,
        "merchant_key": normalize_merchant_key(parsed_merchant),
    }
