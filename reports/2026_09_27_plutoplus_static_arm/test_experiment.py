import importlib.util
from pathlib import Path
import sys

import pytest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import experiment
import evaluate
import run_target


def test_four_rate_inventory_excludes_holdout_and_keeps_primary_depth():
    cases = experiment.selected_cases()
    assert len({c["case_id"] for c in cases}) == len(cases) == 104
    assert {c["split"] for c in cases} == {"dev", "control"}
    for rate, count in zip(experiment.RATES, (32, 32, 8, 8)):
        assert sum(c["rate_hz"] == rate and c["split"] == "dev" for c in cases) == count
        controls = [c for c in cases if c["rate_hz"] == rate and c["split"] == "control"]
        assert len(controls) == 6
        assert {(c["truth"]["kind"], c["edge"]) for c in controls} == {
            (kind, edge) for kind in ("pilot", "noise", "tone") for edge in ("lower", "upper")}


@pytest.mark.parametrize("rate", experiment.RATES)
def test_scratch_bounds_cover_rate_geometry(rate):
    n = round(rate/750)
    fft = 2
    while fft < n:
        fft *= 2
    assert fft <= 32768
    assert 800000/(rate/fft)+2 < 2048
    assert max(round((3+k*26)*rate*4.4e-6)-round((2+k*26)*rate*4.4e-6)
               for k in range(12)) <= 45


def test_source_extension_fixes_three_independent_capacity_assumptions():
    native = experiment.DEPLOY / "src/leo/analysis/native_presence"
    text = experiment.extend_source("presence.c", (native / "presence.c").read_text())
    assert "ALLOC(input, input_capacity)" in text
    assert "frequencies[2048], scores[2048]" in text
    assert "12*23*12" not in text and "CFO_COUNT * 23" not in text
    assert "rate != 7500000 && rate != 10000000" in text
    coarse = experiment.extend_source("coarse_fp32.h", (native / "coarse_fp32.h").read_text())
    assert "symbol*23*12" not in coarse
    assert coarse.count("symbol*45*12") == 3


def test_fail_closed_if_source_patch_no_longer_matches():
    with pytest.raises(ValueError, match="source changed"):
        experiment.extend_source("presence.c", "changed source")


def test_incomplete_timing_receipt_is_not_a_fast_result():
    case = {"case_id": "test", "rate_hz": 2500000, "edge": "lower"}
    result = {**case, "method": "A", "warmups": 1, "repetitions": []}
    with pytest.raises(ValueError, match="incomplete repetitions"):
        evaluate.validate(result, case, "A")


@pytest.mark.parametrize("reference_positive", [False, True])
def test_decision_flip_fails_even_when_identity_proximity_passes(monkeypatch, reference_positive):
    case = {"case_id": "test", "rate_hz": 2500000, "edge": "lower", "split": "dev"}
    monkeypatch.setattr(evaluate, "validate", lambda result, case, method: {
        "science": [{"positive": reference_positive if method != "B" else not reference_positive}],
        "cost": {}})
    monkeypatch.setattr(evaluate.prior, "identity", lambda *args: {"all_identity_gates_pass": True})
    result = evaluate.compare_case(case, {m: {} for m in "ABCD"})
    assert result["identity"]["B"]["all_identity_gates_pass"]
    assert not result["decision_equality"]["B"]
    assert not result["passed"]


def test_rate_phases_are_disjoint_complete_and_keep_negative_controls():
    manifest = {"cases": experiment.selected_cases()}
    low = run_target.select_rates(manifest, [2500000,5000000])
    high = run_target.select_rates(manifest, [7500000,10000000])
    assert len(low["cases"]) == 76 and len(high["cases"]) == 28
    assert {c["case_id"] for c in low["cases"]}.isdisjoint(c["case_id"] for c in high["cases"])
    assert sum(c["split"] == "control" for c in low["cases"]+high["cases"]) == 24
    assert len(manifest["cases"]) == 104
    with pytest.raises(ValueError, match="no input"):
        run_target.select_rates(manifest, [])
