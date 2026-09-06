from app.services.bank_email_parser import detect_direction, parse_bank_email


HDFC_CREDIT = """
Dear Customer,
Greetings from HDFC Bank!
We're writing to inform you that Rs.1000.00 has been successfully credited to your HDFC Bank account ending in 5628.
a. Date: 10-08-26
b. Sender: TUMMALA RAVIBABU (VPA: 9849332966@axl)
c. UPI Reference No.: 760237022940
"""

HDFC_DEBIT = """
Dear Customer, Greetings from HDFC Bank!
Rs.1.00 is debited from your account ending 5628 towards VPA tummalaravi1976@okaxis (TUMMALA RAVIBABU) on 11-08-26.
UPI transaction reference no.: 456616628615.
"""

ICICI_CARD = """
Dear Customer,
Your ICICI Bank Credit Card XX5005 has been used for a transaction of INR 120.00 on Aug 10, 2026 at 08:57:50. Info: UPI-399093374544-VETSA SU.
Available Credit Limit is INR 2,45,953.00. Total Credit Limit is INR 2,50,000.00
"""

HDFC_CC = """
Rs. 1522.00 has been debited from your HDFC Bank Credit Card ending 8308 towards RSP*SWIGGY PVT LTD FOO on 05 Aug, 2026 at 15:46:37.
"""

ICICI_BILL_PAYMENT = """
Payment received on your ICICI Bank Credit Card.
Dear Customer, Aug 06,2026
Greetings from ICICI Bank! We have received payment of INR 12,771.91 on your ICICI Bank Credit Card account 3747 XXXX XXXX 1007 on 06-Aug-2026.
Looking forward to more opportunities to be of service to you. Thank you. Sincerely, ICICI Bank Credit Cards Team.
Any reference to service levels are subject to change at any time at the sole discretion of ICICI Bank or its group companies.
"""

CANARA_DEBIT = """
Dear Customer,
Thanking you for banking with Canara Bank.
An amount of INR 1,023.00 has been DEBITED on 04/08/26 from your account XXX144 to TUMMALA SAI with UPI Ref No.:588439004386. Total Available Balance INR 0.02.
This is an auto generated mail
"""

CANARA_CREDIT = """
Dear Customer,
Thanking you for banking with Canara Bank.
An amount of INR 2,000.00 has been CREDITED on 30/07/26 to your account XXX144 from TUMMALA SAI with UPI Ref No.:391073460866. Total Available Balance INR 8,483.02.
This is an auto generated mail
"""


ICICI_CARD_USER = """
Your ICICI Bank Credit Card XX5005 has been used for a transaction of INR 150.00 on Aug 12, 2026 at 06:40:35. Info: UPI-031175565862-Sri renu.
"""

HDFC_DEBIT_USER = """
Dear Customer,
Greetings from HDFC Bank!
Rs.1.00 is debited from your account ending 5628 towards VPA 7842620363-3@ybl (TUMMALA SAI NAGA VARA PRABHAS) on 11-08-26.
UPI transaction reference no.: 583436094388.
"""


def test_icici_card_sentence_is_debit():
    parsed = parse_bank_email(ICICI_CARD_USER)
    assert parsed["direction"] == "debit"
    assert parsed["amount"] == 150.0
    assert parsed["payment_method"] == "Credit Card"
    assert parsed["upi_ref"] == "031175565862"
    assert "sri renu" in (parsed["merchant"] or "").lower()
    assert parsed["account_suffix"] == "5005"


def test_hdfc_account_debit_sentence():
    parsed = parse_bank_email(HDFC_DEBIT_USER)
    assert parsed["direction"] == "debit"
    assert parsed["amount"] == 1.0
    assert parsed["upi_ref"] == "583436094388"
    assert parsed["account_suffix"] == "5628"
    merch = (parsed["merchant"] or "").upper()
    assert "TUMMALA" in merch or "7842620363-3@YBL" in merch


def test_hdfc_credit_email():
    parsed = parse_bank_email(HDFC_CREDIT)
    assert parsed["direction"] == "credit"
    assert parsed["amount"] == 1000.0
    assert parsed["upi_ref"] == "760237022940"
    assert "RAVIBABU" in (parsed["merchant"] or "").upper()
    assert parsed["category"] == "Income"
    assert parsed["transaction_id"] == "760237022940"


def test_hdfc_debit_email():
    parsed = parse_bank_email(HDFC_DEBIT)
    assert parsed["direction"] == "debit"
    assert parsed["amount"] == 1.0
    assert parsed["upi_ref"] == "456616628615"
    assert "RAVIBABU" in (parsed["merchant"] or "").upper() or "@okaxis" in (parsed["merchant"] or "").lower()


HDFC_AIRTEL_PREPAID = (
    "Rs.349.00 is debited from your account ending 5628 towards "
    "VPA airtel-prepaid.paytm@ptybl (Airtel) on 12-08-26."
)


def test_hdfc_airtel_prepaid_merchant():
    from app.services.bank_email_parser import _parse_amount, _parse_merchant, detect_direction

    assert detect_direction(HDFC_AIRTEL_PREPAID) == "debit"
    assert _parse_amount(HDFC_AIRTEL_PREPAID) == 349.0
    assert (_parse_merchant(HDFC_AIRTEL_PREPAID, "debit") or "").lower() == "airtel"


ICICI_CARD_NO_UPI = """
Dear Customer,
Your ICICI Bank Credit Card XX5005 has been used for a transaction of INR 150.00 on Aug 12, 2026 at 18:42:10. Info: STARBUCKS COFFEE.
Available Credit Limit is INR 2,45,803.00. Total Credit Limit is INR 2,50,000.00
Please do not share your OTP / PIN / CVV with anyone. Click here to unsubscribe.
"""


def test_icici_card_without_upi_ref_is_ingested():
    parsed = parse_bank_email(ICICI_CARD_NO_UPI)
    assert parsed["direction"] == "debit"
    assert parsed["amount"] == 150.0
    assert parsed["payment_method"] == "Credit Card"
    assert parsed["card_issuer"] == "ICICI"
    assert parsed["account_suffix"] == "5005"
    assert "STARBUCKS" in (parsed["merchant"] or "").upper()
    assert parsed["upi_ref"] is None
    assert parsed["transaction_id"]
    assert "150.00" in parsed["transaction_id"]


def test_icici_card_is_debit_not_credit():
    assert detect_direction(ICICI_CARD) == "debit"
    parsed = parse_bank_email(ICICI_CARD)
    assert parsed["direction"] == "debit"
    assert parsed["amount"] == 120.0
    assert "VETSA" in (parsed["merchant"] or "").upper()
    assert parsed["payment_method"] == "Credit Card"
    assert parsed["upi_ref"] == "399093374544"
    assert parsed["transaction_id"] == "399093374544"
    assert parsed["card_issuer"] == "ICICI"
    assert parsed["account_suffix"] == "5005"


def test_hdfc_cc_issuer_and_suffix():
    parsed = parse_bank_email(HDFC_CC)
    assert parsed["payment_method"] == "Credit Card"
    assert parsed["card_issuer"] == "HDFC"
    assert parsed["account_suffix"] == "8308"
    assert "SWIGGY" in (parsed["merchant"] or "").upper()


def test_icici_bill_payment_parses_cycle_anchor():
    from app.services.bank_email_parser import is_cc_bill_payment_email, parse_cc_bill_payment
    from app.services.credit_card_cycle_service import cycle_start_for_bank_payment

    assert is_cc_bill_payment_email("Payment received on your ICICI Bank Credit Card.", ICICI_BILL_PAYMENT)
    bill = parse_cc_bill_payment(ICICI_BILL_PAYMENT)
    assert bill["amount"] == 12771.91
    assert bill["account_suffix"] == "1007"
    cycle = cycle_start_for_bank_payment("ICICI", bill["paid_at"])
    assert cycle.day == 6
    assert cycle.month == 8


def test_hdfc_statement_cycle_on_first():
    from datetime import datetime
    from zoneinfo import ZoneInfo

    from app.services.credit_card_cycle_service import cycle_start_for_bank_payment

    ist = ZoneInfo("Asia/Kolkata")
    paid = datetime(2026, 9, 6, 12, 0, tzinfo=ist)
    cycle = cycle_start_for_bank_payment("HDFC", paid)
    assert cycle.day == 1
    assert cycle.month == 9
    assert cycle.year == 2026


def test_icici_bill_payment_requires_reference():
    import pytest
    from app.services.bank_email_parser import is_real_reference_id

    # Bill-payment ack without UPI/txn ref must not be ingested
    with pytest.raises(ValueError, match="reference"):
        parse_bank_email(ICICI_BILL_PAYMENT)
    assert is_real_reference_id(None) is False
    assert is_real_reference_id("unknown") is False
    assert is_real_reference_id("cc_bill_payment:debit:12771.91:1007:06-aug-2026") is False
    assert is_real_reference_id("588439004386") is True


def test_canara_debit_email():
    parsed = parse_bank_email(CANARA_DEBIT)
    assert parsed["direction"] == "debit"
    assert parsed["amount"] == 1023.0
    assert parsed["upi_ref"] == "588439004386"
    assert parsed["transaction_id"] == "588439004386"
    assert parsed["account_suffix"] == "144"
    assert "TUMMALA" in (parsed["merchant"] or "").upper()
    assert parsed["category"] is None  # spend category decided later


def test_canara_credit_email():
    parsed = parse_bank_email(CANARA_CREDIT)
    assert parsed["direction"] == "credit"
    assert parsed["amount"] == 2000.0
    assert parsed["upi_ref"] == "391073460866"
    assert parsed["transaction_id"] == "391073460866"
    assert parsed["account_suffix"] == "144"
    assert "TUMMALA" in (parsed["merchant"] or "").upper()
    assert parsed["category"] == "Income"


DECLINED = """
Dear Customer,
Your UPI transaction of INR 1,500.00 to MERCHANT XYZ has been DECLINED due to incorrect PIN.
UPI Ref No.: 999888777666
"""

REJECTED = """
Dear Customer,
Transaction of Rs.800.00 was rejected. Please try again later.
"""

OTP_ONLY = """
Dear Customer,
Your OTP for UPI payment of INR 200.00 is 482913. Do not share with anyone.
"""


def test_declined_email_is_skipped():
    from app.services.bank_email_parser import is_bank_alert_email, is_money_movement_email
    import pytest

    assert is_money_movement_email("UPI Alert", DECLINED) is False
    assert is_bank_alert_email("UPI Alert", DECLINED) is False
    with pytest.raises(ValueError):
        parse_bank_email(DECLINED)


def test_rejected_and_otp_emails_are_skipped():
    from app.services.bank_email_parser import is_money_movement_email

    assert is_money_movement_email("Alert", REJECTED) is False
    assert is_money_movement_email("OTP", OTP_ONLY) is False
