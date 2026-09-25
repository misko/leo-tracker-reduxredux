import importlib.util
import json
from pathlib import Path

import numpy as np

MODULE_PATH = Path(__file__).with_name("analyze.py")
SPEC = importlib.util.spec_from_file_location("cross_track_adjacent_replication", MODULE_PATH)
assert SPEC and SPEC.loader
ANALYSIS = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(ANALYSIS)


def synthetic_series(boundary_jump_rad: float) -> dict:
    left = np.arange(0.0, 0.080, 0.002)
    right = np.arange(0.120, 0.200, 0.002)
    time_s = np.concatenate([left, right])
    visit_index = np.concatenate(
        [np.full(len(left), 10), np.full(len(right), 11)]
    )
    cycles = 8.0 * time_s + 0.5 * 3.0 * time_s**2
    phase = 2 * np.pi * cycles
    phase[visit_index == 11] += boundary_jump_rad
    return {
        "time_s": time_s,
        "phasor": np.exp(1j * phase),
        "coherence": np.ones_like(time_s),
        "visit_index": visit_index,
    }


def test_boundary_is_not_used_by_frequency_fit() -> None:
    first = ANALYSIS.fit_increment_model(synthetic_series(0.20), degree=2)
    second = ANALYSIS.fit_increment_model(synthetic_series(-0.35), degree=2)

    assert np.allclose(first["coefficients"], second["coefficients"], atol=1e-10)
    assert abs(first["boundary_residual_deg"] - np.degrees(0.20)) < 1e-8
    assert abs(second["boundary_residual_deg"] - np.degrees(-0.35)) < 1e-8


def test_frozen_selection_has_eight_consecutive_pairs() -> None:
    selection = json.loads(MODULE_PATH.with_name("selection.json").read_text())
    pairs = sum(
        (ANALYSIS.consecutive_pairs(track["selected_visits"]) for track in selection["tracks"]),
        [],
    )

    assert len(selection["tracks"]) == 5
    assert len(pairs) == 8


def test_persisted_replication_preserves_constraints_and_rejects_uniform_reset() -> None:
    result = json.loads(MODULE_PATH.with_name("results.json").read_text())

    assert result["estimator"]["relative_timing_delay_samples"] == 0
    assert result["estimator"]["complex_channel_response_used"] is False
    assert result["estimator"]["phase_intercept_used"] is False
    assert result["estimator"]["boundary_increment_used_in_fit"] is False
    assert result["summary"]["track_count"] == 5
    assert result["summary"]["pair_count"] == 8
    assert result["summary"]["modeled_boundary_resultant"] > 0.9
    assert result["summary"]["uniform_phase_null"]["plus_one_tail_probability"] < 1e-3
