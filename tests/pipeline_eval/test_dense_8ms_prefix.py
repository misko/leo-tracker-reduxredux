from importlib import import_module
from pathlib import Path

import pytest


@pytest.fixture
def planner(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / "reports/ALGO08/v3"))
    return import_module("dense_8ms_prefix")


@pytest.fixture
def prefix():
    factor = dict(candidate_rank=0, integer_epoch_sample=200, passed_fractional_margin_gate=True,
                  fractional_control_score=.1, fractional_exact_score=.2, fractional_margin=.1,
                  fractional_epoch_offset_samples=.25, fractional_tracking_cfo_hz=-120.0)
    rows = [dict(visit_index=visit, receiver_id=radio, channel=1, actual_rf_hz=11.5e9,
                 valid_start_counter=1_000_000 * visit, edge="lower", candidates=[dict(factor)])
            for visit in range(3) for radio in (0, 1)]
    native = dict(source=dict(probes=rows), provenance=dict(processed_windows=3, window_count=3, invalid_capture=0))
    return native, rows[:4]


def test_splice_keeps_original_anchor_and_suffix_and_can_emit_true_empty(planner, prefix):
    native, original = prefix
    replacements = [*original[:2], dict(original[2], candidates=[]), original[3]]
    rows, ledger = planner.splice(native, original, replacements, limit=2)
    assert rows[:2] == original[:2]
    assert rows[2]["candidates"] == []
    assert rows[4:] == native["source"]["probes"][4:]
    assert [event["aperture"] for event in ledger] == ["anchor", "anchor", "short", "short"]


@pytest.mark.parametrize("defect,message", [("changed_anchor", "anchor"), ("changed_rf", "clock or RF"),
                                             ("missing_lane", "missing a lane"), ("changed_12ms", "full 12 ms"),
                                             ("missing_cfo", "signed native fields")])
def test_splice_rejects_missing_or_different_measurements(planner, prefix, defect, message):
    native, original = prefix
    saved = list(original)
    if defect == "changed_anchor":
        saved[0] = dict(saved[0], candidates=[])
    elif defect == "changed_rf":
        saved[3] = dict(saved[3], actual_rf_hz=9e9)
    elif defect == "missing_lane":
        saved.pop()
    elif defect == "changed_12ms":
        original[2] = dict(original[2], candidates=[])
    elif defect == "missing_cfo":
        factor = dict(saved[2]["candidates"][0])
        del factor["fractional_tracking_cfo_hz"]
        saved[2] = dict(saved[2], candidates=[factor])
    with pytest.raises(ValueError, match=message):
        planner.splice(native, original, saved, limit=2)
