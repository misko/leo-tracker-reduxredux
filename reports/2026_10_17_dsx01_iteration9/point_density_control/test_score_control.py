"""Pre-outcome gate direction and immutable-seal tests; no corpus values."""

import pytest
import score_control as score


def fixture():
    audit = dict(feasible=True, accepted=True)
    return {
        "fitted-c": dict(
            audits=dict(legacy=audit.copy(), new_point=audit.copy()),
            original_shared=dict(
                held=dict(current_nll=99.0, original_nll=100.0, associated=11, original=10),
                requested_held=dict(associated=6, original=5),
            ),
        )
    }


def test_gate_new_point_must_improve_legacy_not_reverse():
    rows = fixture()
    blocks = [
        dict(arm="fitted-c", delta_original_shared_nll=-1.0 if i < 4 else 0.1) for i in range(7)
    ]
    assert score.gate(rows, blocks)["passed"]
    rows["fitted-c"]["original_shared"]["held"]["current_nll"] = 101.0
    assert not score.gate(rows, blocks)["passed"]


def test_gate_requires_both_strict_full_denominators_and_four_blocks():
    rows = fixture()
    blocks = [dict(arm="fitted-c", delta_original_shared_nll=-1.0) for _ in range(7)]
    rows["fitted-c"]["audits"]["legacy"]["accepted"] = False
    assert not score.gate(rows, blocks)["passed"]
    rows["fitted-c"]["audits"]["legacy"]["accepted"] = True
    rows["fitted-c"]["original_shared"]["requested_held"]["associated"] = 4
    assert not score.gate(rows, blocks)["passed"]
    assert not score.gate(fixture(), blocks[:4])["passed"]


def test_missing_control_seal_prevents_measurement_reads(tmp_path):
    with pytest.raises(FileNotFoundError):
        score.checked(tmp_path, "predictions_seal.json", "predictions", score.control.CASES)
