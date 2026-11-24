from importlib import import_module
from pathlib import Path

import pytest


@pytest.fixture
def trial(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / "reports/ALGO08/v3"))
    return import_module("independent_8ms_0169")


def test_substitution_preserves_rank_one_native_suffix(trial):
    original = dict(visit_index=0, receiver_id=0, actual_rf_hz=12e9, candidates=[])
    suffix = dict(original, visit_index=64, candidates=[dict(candidate_rank=1)])
    replacement = dict(original, candidates=[dict(candidate_rank=0)])
    source = dict(source=dict(probes=[original, suffix]))
    after = trial.substitution(source, dict(source=dict(probes=[replacement])))
    assert after == [replacement, suffix]
    assert after[1] is suffix


@pytest.mark.parametrize("defect", ["changed_rf", "missing_lane", "interleaved_suffix"])
def test_substitution_rejects_changed_opportunities(trial, defect):
    original = dict(visit_index=0, receiver_id=0, actual_rf_hz=12e9, candidates=[])
    suffix = dict(original, visit_index=64)
    probes, measured = [original, suffix], [original]
    if defect == "changed_rf":
        measured = [dict(original, actual_rf_hz=10e9)]
    elif defect == "missing_lane":
        measured = []
    elif defect == "interleaved_suffix":
        probes = [suffix, original]
    with pytest.raises(ValueError, match="changes opportunities or chronology"):
        trial.substitution(dict(source=dict(probes=probes)), dict(source=dict(probes=measured)))


def test_reject_different_full_anchor_bytes(trial):
    packet = dict(source=dict(probes=[dict(candidates=[])]))
    first = dict(packet=packet, native_schedule=dict(native_calls={"full": 16, "short_primary": 86}),
                 trace=[dict(mode="full", visit=0, lane=0, factors=[1])])
    second = dict(first, trace=[dict(mode="full", visit=0, lane=0, factors=[2])])
    with pytest.raises(ValueError, match="full two-scan anchor changed"):
        trial.verify_apertures(first, second)
