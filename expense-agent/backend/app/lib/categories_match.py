"""Map spoken answers onto spend category names."""

from __future__ import annotations

import re
from typing import Optional

WEAK_CATEGORIES = {"personal", "other", "unknown", "misc", "miscellaneous", "needs you"}

PERSON_PAYEE_RE = re.compile(r"^[A-Za-z][A-Za-z .']{2,80}$")
BRANDISH_RE = re.compile(
    r"[*]|\d{3,}|"
    r"swiggy|zomato|amazon|flipkart|myntra|uber|zepto|blinkit|paytm|phonepe|"
    r"cinemas?|\bpvr\b|inox|services?|\bmart\b|store|\bbank\b|\bltd\b|\bpvt\b|"
    r"limited|fuels?|petrol|pharmacy|hospital|clinic|hotel|restaurant|cafe|"
    r"motors?|electronics|traders?|enterprises|solutions|technologies|"
    r"airtel|jio|\bvi\b|bsnl|irctc|makemytrip",
    re.I,
)


def is_weak_category(name: Optional[str]) -> bool:
    return (name or "").strip().lower() in WEAK_CATEGORIES


def looks_like_person_payee(merchant: Optional[str]) -> bool:
    text = (merchant or "").strip()
    if not text or BRANDISH_RE.search(text):
        return False
    parts = [p for p in re.split(r"\s+", text) if p]
    if len(parts) < 2:
        return False
    return bool(PERSON_PAYEE_RE.match(text))


BUILT_INS = [
    "Food",
    "Groceries",
    "Entertainment",
    "Fuel",
    "Transport",
    "Shopping",
    "Bills",
    "Recharge",
    "Health",
    "Transfer",
    "Self Transfer",
    "Personal",
    "Other",
    "Income",
]

ALIASES = {
    "food": "Food",
    "eat": "Food",
    "eating": "Food",
    "swiggy": "Food",
    "zomato": "Food",
    "grocery": "Groceries",
    "groceries": "Groceries",
    "kirana": "Groceries",
    "movie": "Entertainment",
    "movies": "Entertainment",
    "entertainment": "Entertainment",
    "petrol": "Fuel",
    "diesel": "Fuel",
    "fuel": "Fuel",
    "uber": "Transport",
    "ola": "Transport",
    "taxi": "Transport",
    "transport": "Transport",
    "shopping": "Shopping",
    "amazon": "Shopping",
    "bill": "Bills",
    "bills": "Bills",
    "rent": "Bills",
    "recharge": "Recharge",
    "prepaid": "Recharge",
    "dth": "Recharge",
    "health": "Health",
    "medical": "Health",
    "pharmacy": "Health",
    "transfer": "Transfer",
    "self transfer": "Self Transfer",
    "self": "Self Transfer",
    "persona": "Personal",
    "personal": "Personal",
    "other": "Other",
    "misc": "Other",
    "miscellaneous": "Other",
    "income": "Income",
}


def match_spoken_category(spoken: str, known: list[str] | None = None) -> Optional[str]:
    text = (spoken or "").strip()
    if not text:
        return None
    lower = re.sub(r"[^a-z0-9 &'-]+", " ", text.lower())
    lower = re.sub(r"\s+", " ", lower).strip()
    if lower in {"um", "uh", "hmm", "ah", "huh", "what", "sorry"}:
        return None

    names = list(BUILT_INS)
    for name in known or []:
        if name and name.lower() not in {n.lower() for n in names}:
            names.append(name)

    if lower in ALIASES:
        return ALIASES[lower]

    for name in names:
        key = name.lower()
        if lower == key or key in lower or lower in key:
            return name

    words = lower.split()
    if 1 <= len(words) <= 4 and re.fullmatch(r"[a-z][a-z0-9 &'-]{0,40}", lower):
        return text.strip().title()
    return None
