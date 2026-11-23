from hashlib import sha256

import pytest

from reports.ALGO08.v3.prospective_small_physical import checked, full_stall, issues, ranked_cases


def test_preassignment_uses_only_count_then_id_and_original_range():
    completed = {"DS30-0010": 3000, "DS30-0008": 399, "DS30-0057": 2717,
                 "DS30-0300": 400, "DS30-0200": 400, "DS30-0316": 3042}
    assert ranked_cases(completed, ("DS30-0057",), 400, 3000) == [
        (400, "DS30-0200"), (400, "DS30-0300"), (3000, "DS30-0010")]
    assert ranked_cases({"DS30-0057": 2717, "DS30-0316": 3042}, ("DS30-0057",), 400, 3000) == []


def psi(value):
    return f"some avg10=41.00 avg60=1.00 total=20\nfull avg10={value} avg60=100.00 total=10\n"


def test_admission_requires_complete_payload_and_index_pages_and_both_pressure_checks():
    resident = dict(unavailable={}, members=48, observed_members=48, cached_pages=2000, observed_file_pages=2000)
    assert full_stall(psi(10.0)) == 10.0
    assert issues(resident, resident, (psi(9.99), psi(10.0))) == []
    assert issues(resident | {"cached_pages": 0}, resident | {"unavailable": {"EACCES": 1}},
                  (psi(11.0), psi(7.0))) == ["payload_pages_missing", "index_page_observation_incomplete",
                                             "full_io_stall_above_10_percent"]


def test_frozen_metadata_hash_is_checked(tmp_path):
    path = tmp_path / "pair.json"
    path.write_bytes(b"saved")
    pin = "sha256:"+sha256(b"saved").hexdigest()
    assert checked(path, pin) == b"saved"
    path.write_bytes(b"changed")
    with pytest.raises(ValueError, match="authority differs"):
        checked(path, pin)
