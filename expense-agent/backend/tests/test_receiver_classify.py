from app.lib.receiver_classify import classify_receiver, expand_vpa


AIRTEL_MAIL = (
    "Rs.349.00 is debited from your account ending 5628 towards "
    "VPA airtel-prepaid.paytm@ptybl (Airtel) on 12-08-26."
)


def test_airtel_prepaid_vpa_is_recharge():
    result = classify_receiver("Airtel", [AIRTEL_MAIL])
    assert result is not None
    assert result["category"] == "Recharge"
    assert result["source"] == "receiver"


def test_airtel_prepaid_vpa_without_display_name():
    result = classify_receiver("airtel-prepaid.paytm@ptybl", [AIRTEL_MAIL])
    assert result is not None
    assert result["category"] == "Recharge"


def test_jio_prepaid_is_recharge():
    result = classify_receiver(
        "Jio",
        ["Rs.199.00 is debited towards VPA jio-prepaid.paytm@ptybl (Jio)"],
    )
    assert result is not None
    assert result["category"] == "Recharge"


def test_person_name_is_not_receiver_classified():
    assert classify_receiver("KORIMI BHARGAVI", ["towards VPA bhargavi@okaxis (KORIMI BHARGAVI)"]) is None


def test_paytm_psp_token_is_stripped():
    assert "paytm" not in expand_vpa("airtel-prepaid.paytm@ptybl")
    assert "airtel" in expand_vpa("airtel-prepaid.paytm@ptybl")
    assert "prepaid" in expand_vpa("airtel-prepaid.paytm@ptybl")
