"""Parse Indian bank/UPI/credit-card alert emails into structured payments."""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any, Literal, Optional

from app.services.payment_parser import parse_payment_text

Direction = Literal["credit", "debit"]

# HDFC / Canara / generic bank credit
CREDIT_PATTERNS = [
    re.compile(r"has been successfully\s+credited\s+to your", re.I),
    re.compile(r"\bcredited\s+to your\s+(?:HDFC\s+Bank\s+)?account", re.I),
    re.compile(r"\bis credited to your account", re.I),
    re.compile(r"\bhas been\s+CREDITED\b", re.I),
    re.compile(r"\bcredit(?:ed)?\s+(?:of|for)\s+(?:Rs\.?|INR|₹)", re.I),
    re.compile(r"Rs\.?\s*[0-9,.]+\s+has been successfully credited", re.I),
]

# Account debit (money leaving savings/current account)
DEBIT_PATTERNS = [
    # HDFC: "Rs.1.00 is debited from your account ending 5628 towards VPA ..."
    re.compile(r"Rs\.?\s*[0-9,.]+\s+is debited from your account ending", re.I),
    re.compile(r"\bis debited from your account", re.I),
    re.compile(r"\bhas been debited from your", re.I),
    re.compile(r"\bdebited from your (?:HDFC\s+Bank\s+)?account", re.I),
    re.compile(r"\bhas been\s+DEBITED\b", re.I),
    re.compile(r"\bdebited\s+from\s+A/?c", re.I),
]

# Credit CARD spend (this is an expense / debit, NOT an account credit)
CARD_SPEND_PATTERNS = [
    # ICICI: "Your ICICI Bank Credit Card XX5005 has been used for a transaction of INR 150.00"
    re.compile(
        r"Your ICICI Bank Credit Card\s+\S+\s+has been used for a transaction of",
        re.I,
    ),
    re.compile(r"Credit\s+Card\s+\S+\s+has been used for a transaction of", re.I),
    re.compile(r"used for a transaction of\s+(?:INR|Rs\.?|₹)", re.I),
    re.compile(r"spent on your\s+.*credit\s+card", re.I),
    re.compile(r"transaction of\s+(?:INR|Rs\.?|₹)\s*[0-9,]+\.?[0-9]*.*credit\s+card", re.I),
    # HDFC InstaAlerts: "Rs. 1522.00 has been debited from your HDFC Bank Credit Card ending 8308 towards ..."
    re.compile(r"debited from your\s+HDFC\s+Bank\s+Credit\s+Card", re.I),
    # Generic: "debited from your ... Credit Card ending ..."
    re.compile(r"debited from your\s+\S+.*Credit\s+Card\s+ending", re.I),
    # "A payment was made using your Credit Card"
    re.compile(r"payment was made using your\s+(?:\w+\s+)*Credit\s+Card", re.I),
]

# HDFC CC card spend: "towards MERCHANT_NAME on DD Aug YYYY at HH:MM:SS"
HDFC_CC_MERCHANT_RE = re.compile(
    r"towards\s+([A-Z][A-Z0-9 *&'._/-]{2,60?}?)\s+on\s+\d{2}\s+[A-Za-z]{3}",
    re.I,
)

# HDFC CC datetime: "on 05 Aug, 2026 at 15:46:37"
HDFC_CC_DATE_RE = re.compile(
    r"on\s+(\d{2}\s+[A-Za-z]{3},?\s+\d{4})\s+at\s+(\d{1,2}:\d{2}:\d{2})",
    re.I,
)
# ICICI CC datetime: "on Aug 12, 2026 at 18:42:00"
ICICI_CC_DATE_RE = re.compile(
    r"on\s+([A-Za-z]{3}\s+\d{1,2},?\s+\d{4})\s+at\s+(\d{1,2}:\d{2}:\d{2})",
    re.I,
)

AMOUNT_PATTERNS = [
    re.compile(
        r"(?:Rs\.?|INR|₹)\s*([0-9]+(?:,[0-9]{2,3})*(?:\.[0-9]{1,2})?)",
        re.I,
    ),
    re.compile(
        r"transaction of\s+(?:INR|Rs\.?|₹)\s*([0-9]+(?:,[0-9]{2,3})*(?:\.[0-9]{1,2})?)",
        re.I,
    ),
]

MERCHANT_PATTERNS = [
    # Canara debit: ... from your account XXX144 to NAME with UPI Ref
    re.compile(
        r"from your account\s+\S+\s+to\s+([A-Za-z][A-Za-z0-9 .'-]{1,60}?)\s+with\s+UPI\s+Ref",
        re.I,
    ),
    # Canara credit: ... to your account XXX144 from NAME with UPI Ref
    re.compile(
        r"to your account\s+\S+\s+from\s+([A-Za-z][A-Za-z0-9 .'-]{1,60}?)\s+with\s+UPI\s+Ref",
        re.I,
    ),
    # HDFC debit: towards VPA 7842620363-3@ybl (TUMMALA SAI NAGA VARA PRABHAS)
    re.compile(
        r"towards\s+VPA\s+([A-Za-z0-9._+-]+@[A-Za-z0-9._-]+)(?:\s*\(([^)]+)\))?",
        re.I,
    ),
    # HDFC debit: towards VPA xxx@bank (NAME)
    re.compile(
        r"towards\s+(?:VPA\s+)?([A-Za-z0-9._+-]+@[A-Za-z0-9._-]+)(?:\s*\(([^)]+)\))?",
        re.I,
    ),
    # HDFC credit: Sender: NAME (VPA: ...)
    re.compile(r"Sender:\s*([A-Za-z0-9][A-Za-z0-9 ._-]{1,80}?)(?:\s*\(|$)", re.I),
    # ICICI card Info: UPI-ref-MERCHANT (stop before ". The Available Credit Limit…")
    re.compile(
        r"Info:\s*UPI-\d+-([A-Za-z][A-Za-z0-9 &'_-]*?)(?:\.\s*(?:The\s+)?Available Credit Limit|$)",
        re.I,
    ),
    re.compile(r"Info:\s*([A-Za-z][A-Za-z0-9 &'_-]{1,40})", re.I),
    re.compile(r"paid to\s+([A-Za-z0-9][A-Za-z0-9 &.@'_-]{1,80})", re.I),
]

# Detect HDFC CC email (no UPI ref — uses amount+card+datetime fingerprint)
HDFC_CC_ALERT_RE = re.compile(
    r"debited from your\s+HDFC\s+Bank\s+Credit\s+Card|"
    r"payment was made using your\s+(?:\w+\s+)*Credit\s+Card.*HDFC",
    re.I,
)

UPI_REF_PATTERNS = [
    re.compile(r"UPI\s+Ref\s+No\.?\s*:?\s*([0-9A-Za-z]+)", re.I),
    re.compile(r"UPI\s+(?:transaction\s+)?reference\s+no\.?\s*:?\s*([0-9A-Za-z]+)", re.I),
    re.compile(r"UPI\s+Reference\s+No\.?\s*:?\s*([0-9A-Za-z]+)", re.I),
    re.compile(r"Info:\s*UPI-([0-9]{6,})-", re.I),
    re.compile(r"(?:RRN|UTR|Txn(?:n)?\s*ID|Transaction\s*ID)\s*[:#]?\s*([0-9A-Za-z]{6,})", re.I),
    re.compile(r"\bUPI-([0-9]{6,})-", re.I),
]

ACCOUNT_PATTERNS = [
    re.compile(r"your account\s+(?:X{2,}|\*+)(\d{3,6})", re.I),
    re.compile(r"account ending(?:\s+in)?\s*([0-9]{3,6})", re.I),
    re.compile(r"Credit\s+Card\s+ending\s+([0-9]{3,6})", re.I),
    re.compile(r"Credit\s+Card\s+(?:XX)?([0-9]{4})", re.I),
    re.compile(r"Credit Card account\s+\d{4}\s*X+\s*X+\s*([0-9]{3,4})", re.I),
    re.compile(r"A/?c\s*(?:XX|X*)\s*([0-9]{3,6})", re.I),
]

DATE_KEY_PATTERNS = [
    re.compile(r"on\s+(\d{2}-[A-Za-z]{3}-\d{4})", re.I),
    re.compile(r"Date:\s*(\d{2}-\d{2}-\d{2,4})", re.I),
    re.compile(r"on\s+(\d{2}/\d{2}/\d{2,4})", re.I),
    re.compile(r"on\s+(\d{2}-\d{2}-\d{2,4})", re.I),
    re.compile(r"\b([A-Za-z]{3}\s+\d{1,2},?\s+\d{4})\b"),
]

CC_BILL_SUBJECT_RE = re.compile(r"payment received on your.*credit\s+card", re.I)

JUNK_MERCHANT_RE = re.compile(
    r"("
    r"opportunities to be of service|sole discretion|available credit limit|"
    r"primary card holder|system generated|confidentiality|sincerely|"
    r"looking forward|greetings from|dear customer|nbsp|trade mark|"
    r"^the\b|^\d+$"
    r")",
    re.I,
)


def detect_direction(text: str) -> Direction:
    # Card spend first — "Credit Card" must not be treated as money credited
    for pattern in CARD_SPEND_PATTERNS:
        if pattern.search(text):
            return "debit"
    for pattern in CREDIT_PATTERNS:
        if pattern.search(text):
            return "credit"
    for pattern in DEBIT_PATTERNS:
        if pattern.search(text):
            return "debit"
    # Fallback: explicit words
    if re.search(r"\bcredited\b", text, re.I) and not re.search(r"credit\s+card", text, re.I):
        return "credit"
    return "debit"


def _parse_amount(text: str) -> Optional[float]:
    for pattern in AMOUNT_PATTERNS:
        match = pattern.search(text)
        if match:
            try:
                return float(match.group(1).replace(",", ""))
            except ValueError:
                continue
    return None


def is_junk_merchant(merchant: Optional[str]) -> bool:
    if not merchant:
        return True
    value = merchant.strip()
    if len(value) < 2 or len(value) > 80:
        return True
    if value.isdigit():
        return True
    if JUNK_MERCHANT_RE.search(value):
        return True
    return False


def strip_credit_limit_suffix(value: str) -> str:
    """Remove ICICI/HDFC trailing 'Available Credit Limit…' spam from merchant names."""
    value = re.sub(r"\s+", " ", value).strip(" .,-")
    value = re.sub(
        r"\.?\s*(?:The\s+)?Available Credit Limit\b.*$",
        "",
        value,
        flags=re.I,
    ).strip(" .,-")
    value = re.sub(r"\s+on your card\b.*$", "", value, flags=re.I).strip(" .,-")
    value = re.sub(r"\s+Total Credit Limit\b.*$", "", value, flags=re.I).strip(" .,-")
    return value


def _clean_merchant_value(value: str) -> Optional[str]:
    value = strip_credit_limit_suffix(value)
    lower = value.lower()
    if lower in {"vpa", "upi", "info", "customer", "hdfc bank", "icici bank"}:
        return None
    if is_junk_merchant(value):
        return None
    return value[:255]


def _parse_hdfc_cc_merchant(text: str) -> Optional[str]:
    """Extract merchant from HDFC CC InstaAlert: 'towards RSP*SWIGGY PVT LTD FOO on 05 Aug'."""
    m = HDFC_CC_MERCHANT_RE.search(text)
    if m:
        value = m.group(1).strip().rstrip("*. -")
        cleaned = _clean_merchant_value(value)
        if cleaned:
            return cleaned
    # Fallback: "towards MERCHANT" anywhere before a date/newline
    m2 = re.search(r"towards\s+([A-Z][A-Z0-9 *&'._/-]{2,60}?)(?:\s+on\s+\d|\s*$)", text, re.I)
    if m2:
        value = m2.group(1).strip().rstrip("*. -")
        cleaned = _clean_merchant_value(value)
        if cleaned:
            return cleaned
    return None


def is_hdfc_cc_alert(text: str) -> bool:
    """True for HDFC InstaAlerts about Credit Card spends (no UPI ref)."""
    return bool(HDFC_CC_ALERT_RE.search(text))


def is_card_spend_alert(text: str) -> bool:
    """True for ICICI/HDFC credit-card spend alerts, with or without a UPI ref."""
    return is_hdfc_cc_alert(text) or any(pattern.search(text) for pattern in CARD_SPEND_PATTERNS)


def detect_credit_card_issuer(text: str) -> Optional[str]:
    """Return HDFC or ICICI when the email is a credit card alert."""
    if not text or not re.search(r"credit\s+card", text, re.I):
        return None
    if re.search(r"HDFC\s+Bank", text, re.I) or is_hdfc_cc_alert(text):
        return "HDFC"
    if re.search(r"ICICI\s+Bank", text, re.I):
        return "ICICI"
    return None


def _parse_merchant(text: str, direction: Direction) -> Optional[str]:
    # Card bill payment acknowledgements are not merchant spends
    if re.search(r"received payment of|payment received on your\s+.*credit\s+card", text, re.I):
        return "ICICI Credit Card Bill Payment"

    # HDFC CC alerts: "towards MERCHANT on DD Mon YYYY"
    if is_hdfc_cc_alert(text):
        hdfc_merchant = _parse_hdfc_cc_merchant(text)
        if hdfc_merchant:
            return hdfc_merchant

    for pattern in MERCHANT_PATTERNS:
        match = pattern.search(text)
        if not match:
            continue
        # towards VPA ... (NAME) → prefer NAME
        if match.lastindex and match.lastindex >= 2 and match.group(2):
            value = match.group(2).strip()
        else:
            value = match.group(1).strip()
        cleaned = _clean_merchant_value(value)
        if cleaned:
            return cleaned
    return None


def _parse_upi_ref(text: str) -> Optional[str]:
    for pattern in UPI_REF_PATTERNS:
        match = pattern.search(text)
        if match:
            return match.group(1)
    return None


def _parse_account_suffix(text: str) -> Optional[str]:
    for pattern in ACCOUNT_PATTERNS:
        match = pattern.search(text)
        if match:
            return match.group(1)
    return None


def _parse_date_key(text: str, timestamp: Optional[datetime] = None) -> Optional[str]:
    for pattern in DATE_KEY_PATTERNS:
        match = pattern.search(text)
        if match:
            return re.sub(r"[\s,]+", "-", match.group(1).strip().lower())
    if timestamp is not None:
        return timestamp.strftime("%Y-%m-%d")
    return None


def _parse_cc_datetime_key(text: str) -> Optional[str]:
    """Extract a fine-grained fingerprint key from ICICI/HDFC card-spend timestamps."""
    for pattern in (HDFC_CC_DATE_RE, ICICI_CC_DATE_RE):
        m = pattern.search(text)
        if m:
            date_part = re.sub(r"[\s,]+", "", m.group(1))
            time_part = m.group(2).replace(":", "")
            return f"{date_part}-{time_part}"
    return None


def build_payment_fingerprint(
    *,
    amount: float,
    direction: Direction,
    upi_ref: Optional[str],
    account_suffix: Optional[str],
    date_key: Optional[str],
    channel: str,
    time_key: Optional[str] = None,
) -> str:
    """Stable id used to merge duplicate bank emails for one real payment."""
    if upi_ref:
        return f"upi:{upi_ref}"
    parts = [
        channel or "payment",
        direction,
        f"{float(amount):.2f}",
        account_suffix or "na",
        time_key or date_key or "na",
    ]
    return ":".join(parts)


def is_real_reference_id(value: Optional[str]) -> bool:
    """True for bank/UPI refs — false for missing, Unknown, or synthetic fingerprints."""
    if not value:
        return False
    ref = str(value).strip()
    if not ref:
        return False
    lower = ref.lower()
    if lower in {"unknown", "n/a", "na", "none", "null", "-"}:
        return False
    if lower.startswith("upi:"):
        ref = ref.split(":", 1)[1].strip()
        if not ref:
            return False
    # Synthetic fingerprints look like "cc_bill_payment:debit:12771.91:1007:..."
    if ":" in ref and not re.fullmatch(r"[0-9A-Za-z._-]{6,}", ref.replace(":", "")):
        # Still allow plain UPI-style tokens without channel prefixes
        if re.match(
            r"^(cc_bill_payment|credit_card|bank_debit|bank_credit|payment):",
            lower,
        ):
            return False
    # Must look like a real ref (UPI RRN / txn id), not a short junk token
    if not re.fullmatch(r"[0-9A-Za-z._-]{6,64}", ref):
        return False
    return True


NON_MONETARY_ALERT_RE = re.compile(
    r"("
    r"\bdeclined\b|\brejected\b|\bfailed\b|\bunsuccessful\b|"
    r"not\s+(?:been\s+)?(?:successful|completed|processed)|"
    r"could\s+not\s+be\s+(?:completed|processed|debited|credited)|"
    r"unable\s+to\s+(?:process|complete|debit|credit)|"
    r"transaction\s+(?:is\s+)?(?:cancelled|canceled|expired|pending\s+approval)|"
    r"otp\b|one[\s-]?time\s+password|do\s+not\s+share|"
    r"incorrect\s+pin|wrong\s+pin|invalid\s+(?:pin|otp)|"
    r"standing\s+instruction\s+(?:failed|rejected)|"
    r"insufficient\s+(?:funds|balance)(?!.*\b(?:debited|credited)\b)"
    r")",
    re.I,
)

# Real money movement only — not mere “transaction alert” / credit-limit info
MONEY_MOVEMENT_RE = re.compile(
    r"("
    r"\bhas been\s+CREDITED\b|\bhas been\s+DEBITED\b|"
    r"\b(?:successfully\s+)?credited\b|"
    r"\b(?:is\s+)?debited\b|"
    r"used for a transaction of|"
    r"received payment of|payment received on your|"
    r"\bspent on\b|"
    r"debited from your\s+HDFC\s+Bank\s+Credit\s+Card|"
    r"payment was made using your\s+(?:\w+\s+)*Credit\s+Card|"
    r"(?:Rs\.?|INR|₹)\s*[0-9,]+\.?[0-9]*\s+(?:paid|debited|credited)"
    r")",
    re.I,
)


def _parse_date_from_key(key: str) -> Optional[datetime]:
    from zoneinfo import ZoneInfo

    ist = ZoneInfo("Asia/Kolkata")
    cleaned = re.sub(r"[\s,]+", " ", key.strip())
    for fmt in (
        "%d-%b-%Y",
        "%d-%B-%Y",
        "%d/%m/%y",
        "%d/%m/%Y",
        "%d-%m-%y",
        "%d-%m-%Y",
        "%b %d %Y",
        "%B %d %Y",
    ):
        try:
            return datetime.strptime(cleaned, fmt).replace(tzinfo=ist)
        except ValueError:
            continue
    return None


def is_cc_bill_payment_email(subject: str, body: str) -> bool:
    blob = f"{subject or ''}\n{body or ''}"
    if re.search(r"payment received on your\s+.*credit\s+card", blob, re.I):
        return True
    if re.search(r"received payment of\s+(?:INR|Rs\.?|₹)", blob, re.I) and re.search(
        r"credit\s+card", blob, re.I
    ):
        return True
    return False


def parse_cc_bill_payment(
    raw_text: str,
    *,
    timestamp: Optional[datetime] = None,
) -> dict[str, Any]:
    text = (raw_text or "").strip()
    if not is_cc_bill_payment_email("", text):
        raise ValueError("Not a credit card bill payment email")

    amount = _parse_amount(text)
    if amount is None:
        raise ValueError("Could not parse bill payment amount")

    paid_at: Optional[datetime] = None
    for pattern in DATE_KEY_PATTERNS:
        match = pattern.search(text)
        if match:
            paid_at = _parse_date_from_key(match.group(1))
            if paid_at:
                break
    if paid_at is None and timestamp is not None:
        paid_at = timestamp
    if paid_at is None:
        raise ValueError("Could not parse bill payment date")

    account_suffix = _parse_account_suffix(text)
    issuer = detect_credit_card_issuer(text) or "ICICI"
    return {
        "amount": float(amount),
        "paid_at": paid_at,
        "account_suffix": account_suffix,
        "card_issuer": issuer,
        "description": "Credit card bill payment",
    }


def is_non_monetary_alert(subject: str, body: str) -> bool:
    """Info-only bank mails: declined / rejected / OTP / failed — no money moved."""
    blob = f"{subject or ''}\n{body or ''}"
    if not NON_MONETARY_ALERT_RE.search(blob):
        return False
    # If money clearly moved, keep it; otherwise treat as info-only
    return not MONEY_MOVEMENT_RE.search(blob)


def is_money_movement_email(subject: str, body: str) -> bool:
    """Only true when the mail reports an actual credit/debit/spend."""
    blob = f"{subject or ''}\n{body or ''}"
    if NON_MONETARY_ALERT_RE.search(blob) and not MONEY_MOVEMENT_RE.search(blob):
        return False
    if NON_MONETARY_ALERT_RE.search(blob):
        # e.g. "transaction declined" even if amount appears — skip
        if re.search(
            r"\b(?:declined|rejected|failed|unsuccessful|cancelled|canceled)\b",
            blob,
            re.I,
        ):
            return False
    return bool(MONEY_MOVEMENT_RE.search(blob))


def is_bank_alert_email(subject: str, body: str) -> bool:
    blob = f"{subject}\n{body}"
    if re.search(r"digest|newsletter|unsubscribe|groww digest|statement for the period", subject or "", re.I):
        return False
    if not is_money_movement_email(subject, body):
        return False
    markers = [
        r"credited to your",
        r"debited from your",
        r"is debited from",
        r"has been\s+CREDITED",
        r"has been\s+DEBITED",
        r"Credit Card .+ used for a transaction",
        r"received payment of|payment received on your",
        r"UPI Reference No",
        r"UPI Ref No",
        r"UPI transaction reference",
        r"UPI Transaction Alert",
        r"HDFC Bank",
        r"Canara Bank",
        r"ICICI Bank Credit Card",
        r"InstaAlerts",
    ]
    return any(re.search(p, blob, re.I) for p in markers)


def parse_bank_email(
    raw_text: str,
    *,
    timestamp: Optional[datetime] = None,
) -> dict[str, Any]:
    text = (raw_text or "").strip()
    if not is_money_movement_email("", text):
        raise ValueError("Email is informational only (no credited/debited money movement)")

    direction = detect_direction(text)
    amount = _parse_amount(text)
    if amount is None:
        # Fallback to generic parser amount extraction
        try:
            generic = parse_payment_text(text, source="email", timestamp=timestamp)
            amount = generic["amount"]
        except ValueError as exc:
            raise ValueError("Could not determine payment amount from email") from exc

    merchant = _parse_merchant(text, direction)
    upi_ref = _parse_upi_ref(text)
    account_suffix = _parse_account_suffix(text)
    date_key = _parse_date_key(text, timestamp)
    method = (
        "Credit Card"
        if re.search(r"credit\s+card", text, re.I)
        else ("UPI" if re.search(r"\bUPI\b", text, re.I) else "Bank")
    )

    if direction == "credit":
        category = "Income"
        subcategory = "UPI Credit" if method == "UPI" else "Bank Credit"
        description = f"Credited from {merchant}" if merchant else "Amount credited"
        confidence = 0.97
        channel = "bank_credit"
    elif re.search(r"received payment of|payment received on your\s+.*credit\s+card", text, re.I):
        category = "Bills"
        subcategory = "Credit Card"
        description = "Credit card bill payment"
        confidence = 0.92
        channel = "cc_bill_payment"
        method = "Credit Card"
    elif re.search(r"credit\s+card", text, re.I):
        # Classify by merchant in graph — unknown merchants become Other
        category = None
        subcategory = None
        description = f"Card spend at {merchant}" if merchant else "Credit card transaction"
        confidence = 0.85
        channel = "credit_card"
    else:
        category = None
        subcategory = "UPI Debit" if method == "UPI" else "Bank Debit"
        description = f"Paid to {merchant}" if merchant else "Amount debited"
        confidence = 0.85
        channel = "bank_debit"

    time_key = _parse_cc_datetime_key(text) if is_card_spend_alert(text) else None
    fingerprint = build_payment_fingerprint(
        amount=float(amount),
        direction=direction,
        upi_ref=upi_ref,
        account_suffix=account_suffix,
        date_key=date_key,
        channel=channel,
        time_key=time_key,
    )

    # Card spends often have no UPI ref (POS / Info: MERCHANT) — fingerprint is the id
    card_spend = is_card_spend_alert(text)
    if not is_real_reference_id(upi_ref) and not card_spend:
        raise ValueError("Email has no UPI/transaction reference id — skipping")

    # For CC emails without UPI ref, fingerprint serves as the stable transaction id
    effective_txn_id = upi_ref if is_real_reference_id(upi_ref) else fingerprint

    return {
        "source": "email",
        "direction": direction,
        "amount": float(amount),
        "merchant": merchant,
        "payment_method": method,
        "transaction_id": effective_txn_id,
        "upi_ref": upi_ref,
        "account_suffix": account_suffix,
        "fingerprint": fingerprint,
        "timestamp": timestamp,
        "raw_text": text,
        "category": category,
        "subcategory": subcategory,
        "description": description,
        "confidence": confidence,
        "channel": channel,
        "card_issuer": detect_credit_card_issuer(text) if method == "Credit Card" else None,
    }
