import os

os.environ.setdefault("SELF_OWNER_NAMES", "TUMMALA SAI NAGA VARA PRABHAS")

from app.core.config import get_settings
from app.services.self_transfer import clear_self_transfer_cache, is_self_transfer_merchant


def setup_function():
    get_settings.cache_clear()
    clear_self_transfer_cache()


def test_full_name_is_self():
    assert is_self_transfer_merchant("TUMMALA SAI NAGA VARA PRABHAS")


def test_partial_name_parts_are_self():
    assert is_self_transfer_merchant("TUMMALA SAI")
    assert is_self_transfer_merchant("TUMMALA SAI NAGA")
    assert is_self_transfer_merchant("PRABHAS")
    assert is_self_transfer_merchant("Paid to TUMMALA SAI NAGA")


def test_family_other_person_not_self():
    assert not is_self_transfer_merchant("TUMMALA RAVI BABU")
    assert not is_self_transfer_merchant("TUMMALA RAVIBABU")
    assert not is_self_transfer_merchant("KORIMI BHARGAVI")
    assert not is_self_transfer_merchant("SAI")  # too ambiguous alone
