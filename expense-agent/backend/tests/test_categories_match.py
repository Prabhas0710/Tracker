from app.lib.categories_match import looks_like_person_payee


def test_person_names_are_payees():
    assert looks_like_person_payee("KORIMI BHARGAVI") is True
    assert looks_like_person_payee("PRANAY KIRAN CHOWDARY JALADI") is True


def test_brands_are_not_person_payees():
    assert looks_like_person_payee("PVR Cinemas") is False
    assert looks_like_person_payee("ABC Services") is False
    assert looks_like_person_payee("Swiggy") is False
    assert looks_like_person_payee("RSP*SWIGGY") is False
