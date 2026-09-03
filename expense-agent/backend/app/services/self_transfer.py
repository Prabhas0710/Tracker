"""Detect payments to/from the account owner's own name (self transfers)."""

from __future__ import annotations

import re
from functools import lru_cache
from typing import Iterable, Optional

from app.core.config import get_settings


def _normalize(value: str) -> str:
    value = value.upper().strip()
    value = re.sub(r"[^A-Z0-9\s]", " ", value)
    value = re.sub(r"\s+", " ", value).strip()
    return value


def _tokens(value: str) -> list[str]:
    return [t for t in _normalize(value).split() if t]


@lru_cache
def _owner_phrases() -> tuple[str, ...]:
    settings = get_settings()
    raw = getattr(settings, "self_owner_names", "") or ""
    names = [part.strip() for part in raw.split("|") if part.strip()]
    if not names:
        names = ["TUMMALA SAI NAGA VARA PRABHAS"]

    phrases: set[str] = set()
    for name in names:
        toks = _tokens(name)
        if not toks:
            continue
        full = " ".join(toks)
        phrases.add(full)
        # Consecutive multi-word parts: "TUMMALA SAI", "SAI NAGA", "TUMMALA SAI NAGA", ...
        for width in range(2, len(toks) + 1):
            for i in range(0, len(toks) - width + 1):
                phrases.add(" ".join(toks[i : i + width]))
        # Distinctive single tokens: last name, or long unique tokens (avoid family-only TUMMALA)
        phrases.add(toks[-1])
        for tok in toks:
            if len(tok) >= 8:
                phrases.add(tok)
    # Prefer longer phrases first when matching
    return tuple(sorted(phrases, key=len, reverse=True))


def is_self_transfer_merchant(merchant: Optional[str]) -> bool:
    """True when payee/payer looks like the account owner (self bank transfer)."""
    if not merchant:
        return False
    hay = f" {_normalize(merchant)} "
    for phrase in _owner_phrases():
        needle = f" {phrase} "
        if needle in hay:
            return True
        # Exact merchant equals phrase
        if _normalize(merchant) == phrase:
            return True
    return False


def self_transfer_classification(merchant: Optional[str]) -> dict:
    label = merchant.strip() if merchant else "Self"
    return {
        "category": "Transfer",
        "subcategory": "Self",
        "description": f"Self transfer · {label}",
        "confidence": 0.99,
        "classification_source": "self_transfer",
        "direction": "transfer",
    }


def clear_self_transfer_cache() -> None:
    _owner_phrases.cache_clear()
