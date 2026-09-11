"""Guard frozen factorial coverage and non-oracular historical target selection."""

import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).parents[2] / "tools"))
from replay_historic_glrt_joint import configurations, select_candidate, stratified_shifts
from summarize_historic_glrt_joint import shift_error, validate_inventory


@pytest.mark.parametrize("fs", [2500000, 5000000])
def test_factorial_covers_four_acquisition_pairs_without_changing_other_controls(fs):
    configs = list(configurations(fs).values())
    assert {(c.fine_cfo_step_hz, c.conditioned_cfo_step_hz) for c in configs} == {
        (500, 100),
        (500, 50),
        (250, 100),
        (250, 50),
    }
    assert all(
        c.maximum_probe_samples == fs // 50 and c.retained_candidate_count == 8 for c in configs
    )


def test_shifts_are_reproducible_stratified_and_probe_specific():
    a = np.array(stratified_shifts("one"))
    assert a.tolist() == stratified_shifts("one")
    assert a.tolist() != stratified_shifts("two")
    assert np.array_equal(np.floor((a + 2000) / 500), np.arange(8))


def test_target_selection_does_not_choose_the_closest_cfo():
    candidates = [
        {"rank": 0, "epoch_sample": 10, "cfo_hz": 100.0, "margin": 0.1, "exact_score": 0.2},
        {"rank": 1, "epoch_sample": 11, "cfo_hz": 90000.0, "margin": 0.3, "exact_score": 0.4},
    ]
    assert select_candidate(candidates, 10, 100)["rank"] == 1
    candidates[1]["cfo_hz"] = -70000.0
    assert select_candidate(candidates, 10, 100)["rank"] == 1


def test_circular_target_phase_and_missing_basin_are_explicit():
    candidate = {"rank": 0, "epoch_sample": 99, "cfo_hz": 1.0, "margin": 0.1, "exact_score": 0.2}
    assert select_candidate([candidate], 0, 100) == candidate
    assert select_candidate([candidate], 50, 100) is None
    assert select_candidate([{**candidate, "cfo_hz": None}]) is None


def test_increment_error_reports_alias_branch_changes_separately():
    base = {"target": {"cfo_hz": 100}}
    shifted = {"target": {"cfo_hz": 100 + 137 + 1 / 4.4e-6}, "imposed_shift_hz": 137}
    result = shift_error(shifted, base)
    assert result["alias_adjusted_error_hz"] == pytest.approx(0)
    assert result["raw_error_hz"] == pytest.approx(1 / 4.4e-6)
    assert result["alias_branch_change"] == 1


def test_missing_shift_target_is_not_zero_error():
    assert (
        shift_error({"target": None, "imposed_shift_hz": 50}, {"target": {"cfo_hz": 100}}) is None
    )


@pytest.mark.parametrize("damage", ["missing", "duplicate"])
def test_missing_or_duplicate_shift_case_cannot_enter_summary(damage):
    plan = {"selection": [{"session_id": "scan", "probes": 1, "shifts": {"0": [137.5]}}]}
    rows = [{"index": 0, "imposed_shift_hz": shift, "profile": "profile"} for shift in (0.0, 137.5)]
    docs = [{"session_id": "scan", "rows": rows}]
    validate_inventory(plan, docs, ["profile"])
    if damage == "missing":
        rows.pop()
    else:
        rows.append(rows[-1].copy())
    with pytest.raises(ValueError, match="missing or duplicate"):
        validate_inventory(plan, docs, ["profile"])
