from hashlib import sha256

import pytest

from reports.ALGO08.v3.field_speed_reachability import checked, gates


def test_gates_keep_both_pairing_and_total_budgets():
    cases = [
        {"actual_wall_s": 50, "stock_wall_s": 100},
        {"actual_wall_s": 8, "stock_wall_s": 10},
    ]
    result = gates(cases, [10, 0])
    assert result["saving"] == 10
    assert result["remaining"] == 48
    assert result["sum_ratio"] == 48 / 110
    assert result["paired_median_ratio"] == pytest.approx(0.6)
    assert result["gap_to_half"] == -7


def test_checked_receipt_supports_tagged_seals_and_rejects_changes(tmp_path):
    path = tmp_path / "receipt.json"
    data = b"{}"
    pin = "sha256:" + sha256(data).hexdigest()
    path.write_bytes(data)
    assert checked(path, pin) == data
    path.write_bytes(data + b"\n")
    with pytest.raises(ValueError, match="Seal changed"):
        checked(path, pin)
