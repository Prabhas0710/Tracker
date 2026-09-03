"""Classify a payment from the bank-mail receiver: VPA handle + merchant name."""

from __future__ import annotations

import re
from typing import Any, Optional

VPA_RE = re.compile(r"\b([A-Za-z0-9._+-]+@[A-Za-z0-9._-]+)\b")

# PSP / bank handles are not the merchant
PSP_TOKENS = {
    "paytm",
    "phonepe",
    "gpay",
    "googlepay",
    "ybl",
    "ibl",
    "axl",
    "apl",
    "ptybl",
    "okaxis",
    "okicici",
    "okhdfcbank",
    "okbizaxis",
    "okhdfc",
    "upi",
}

# First match wins. Use VPA local-part tokens (airtel-prepaid.paytm → airtel prepaid).
RECEIVER_RULES: list[tuple[re.Pattern[str], str, str, float]] = [
    (re.compile(r"\b(prepaid|recharge)\b", re.I), "Recharge", "Mobile", 0.98),
    (
        re.compile(
            r"\b(dth|tataplay|tata play|dishtv|dish tv|sundirect|sun direct|\bd2h\b)\b",
            re.I,
        ),
        "Recharge",
        "DTH",
        0.96,
    ),
    (
        re.compile(r"\b(postpaid|broadband|fiber|fibre|\bwifi\b|landline)\b", re.I),
        "Bills",
        "Telecom",
        0.95,
    ),
    (
        re.compile(r"\b(airtel|jio|vodafone|\bvi\b|bsnl|mtnl)\b", re.I),
        "Recharge",
        "Mobile",
        0.93,
    ),
    (
        re.compile(
            r"\b(electricity|bescom|tsspdcl|apspdcl|msedcl|torrent power|adani electricity)\b",
            re.I,
        ),
        "Bills",
        "Electricity",
        0.95,
    ),
    (re.compile(r"\b(indane|hp gas|bharat gas|\blpg\b)\b", re.I), "Bills", "Gas", 0.94),
    (re.compile(r"\b(netflix|spotify|hotstar|sonyliv|prime video|youtube)\b", re.I), "Entertainment", "Streaming", 0.95),
]


def extract_vpas(text: str) -> list[str]:
    return [m.group(1) for m in VPA_RE.finditer(text or "")]


def expand_vpa(vpa: str) -> str:
    local = (vpa or "").split("@", 1)[0].lower()
    tokens = re.split(r"[.\-_+]+", local)
    return " ".join(t for t in tokens if t and t not in PSP_TOKENS)


def receiver_blob(merchant: Optional[str], raw_texts: list[str] | None) -> str:
    parts = [merchant or "", *(raw_texts or [])]
    text = " ".join(parts)
    expanded = [expand_vpa(vpa) for vpa in extract_vpas(text)]
    return " ".join([text, *expanded]).lower()


def classify_receiver(
    merchant: Optional[str],
    raw_texts: list[str] | None = None,
) -> Optional[dict[str, Any]]:
    blob = receiver_blob(merchant, raw_texts)
    if not blob.strip():
        return None
    for pattern, category, subcategory, confidence in RECEIVER_RULES:
        if pattern.search(blob):
            return {
                "category": category,
                "subcategory": subcategory,
                "description": merchant or category,
                "confidence": confidence,
                "source": "receiver",
            }
    return None
