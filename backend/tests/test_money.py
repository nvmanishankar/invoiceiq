import pytest

from app.utils.money import allowed_diff, format_inr, rupees_to_paise, within_tolerance

PCT, CAP = 0.02, 500000  # company defaults: 2%, Rs 5,000


def test_tolerance_on_1_lakh_is_2000():
    assert allowed_diff(rupees_to_paise(100000), PCT, CAP) == rupees_to_paise(2000)


def test_tolerance_on_5_lakh_is_capped_at_5000():
    assert allowed_diff(rupees_to_paise(500000), PCT, CAP) == rupees_to_paise(5000)


def test_within_tolerance():
    expected = rupees_to_paise(100000)
    assert within_tolerance(expected + 200000, expected, PCT, CAP)
    assert not within_tolerance(expected + 200001, expected, PCT, CAP)
    assert within_tolerance(expected - 200000, expected, PCT, CAP)


def test_rupees_to_paise():
    assert rupees_to_paise(118000) == 11800000
    assert rupees_to_paise("0.015") == 2  # half-up
    assert rupees_to_paise(1.005) == 101


@pytest.mark.parametrize(
    "paise,text",
    [
        (11800000, "₹1,18,000"),
        (78116000, "₹7,81,160"),
        (14868000, "₹1,48,680"),
        (0, "₹0"),
        (99900, "₹999"),
        (100000, "₹1,000"),
        (1000000000, "₹1,00,00,000"),
        (11800050, "₹1,18,000.50"),
        (-2360000, "-₹23,600"),
        (None, "—"),
    ],
)
def test_format_inr(paise, text):
    assert format_inr(paise) == text


def test_format_inr_rs_symbol():
    assert format_inr(11800000, symbol="Rs ") == "Rs 1,18,000"
