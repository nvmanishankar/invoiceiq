import json
from pathlib import Path

import pytest

from app.models import CompanySettings, Vendor
from app.utils.gstin import gstin_checksum, pan, state_code, valid_gstin

SEED = Path(__file__).resolve().parent.parent / "app" / "seed_data"


def test_every_seeded_gstin_is_valid(db):
    gstins = [v.tax_id for v in db.query(Vendor)] + [db.query(CompanySettings).one().gstin]
    assert len(gstins) == 7
    for g in gstins:
        assert valid_gstin(g), g


def test_seed_json_gstins_are_valid():
    vendors = json.loads((SEED / "vendors.json").read_text())
    for v in vendors:
        assert valid_gstin(v["tax_id"]), v["tax_id"]


@pytest.mark.parametrize(
    "bad",
    [
        "36AABCA1234F1ZB",  # wrong checksum (valid is ...ZA)
        "99AABCA1234F1Z" + gstin_checksum("99AABCA1234F1Z"),  # state code out of range
        "36AABCA1234F1Y" + gstin_checksum("36AABCA1234F1Y"),  # 14th char must be Z
        "36AABCA1234",  # too short
        "",
        None,
    ],
)
def test_invalid_gstins(bad):
    assert not valid_gstin(bad)


def test_normalises_case_and_spaces():
    assert valid_gstin("36aabca1234f1za")
    assert valid_gstin("36 AABCA 1234F1ZA")


def test_state_code_and_pan():
    assert state_code("29AAFCB5678K1Z1") == "29"
    assert pan("29AAFCB5678K1Z1") == "AAFCB5678K"
