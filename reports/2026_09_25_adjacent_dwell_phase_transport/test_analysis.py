import importlib.util
import json
from pathlib import Path

import numpy as np

MODULE_PATH = Path(__file__).with_name("analyze.py")
SPEC = importlib.util.spec_from_file_location("adjacent_dwell_phase_transport", MODULE_PATH)
assert SPEC and SPEC.loader
ANALYSIS = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(ANALYSIS)


def synthetic_series(boundary_jump_rad: float) -> dict:
    left = np.arange(0.0, 0.080, 0.002)
    right = np.arange(0.120, 0.200, 0.002)
    time_s = np.concatenate([left, right])
    visit_index = np.concatenate(
        [np.full(len(left), 766), np.full(len(right), 767)]
    )
    cycles = 8.0 * time_s + 0.5 * 3.0 * time_s**2
    phase = 2 * np.pi * cycles
    phase[visit_index == 767] += boundary_jump_rad
    return {
        "time_s": time_s,
        "phasor": np.exp(1j * phase),
        "coherence": np.ones_like(time_s),
        "visit_index": visit_index,
    }


def test_boundary_increment_is_held_out_of_frequency_fit() -> None:
    first = ANALYSIS.fit_increment_model(synthetic_series(0.20), degree=2)
    second = ANALYSIS.fit_increment_model(synthetic_series(-0.35), degree=2)

    assert np.allclose(first["coefficients"], second["coefficients"], atol=1e-10)
    assert abs(first["boundary_residual_deg"] - np.degrees(0.20)) < 1e-8
    assert abs(second["boundary_residual_deg"] - np.degrees(-0.35)) < 1e-8


def test_persisted_result_preserves_identity_channel_constraints() -> None:
    result = json.loads(MODULE_PATH.with_name("results.json").read_text())

    assert result["relative_timing_delay_samples"] == 0
    assert result["complex_channel_response_used"] is False
    assert result["per_dwell_phase_intercepts_fitted"] is False
    assert result["global_phase_intercept_used"] is False
    assert result["fit_uses_boundary_increment"] is False
    assert result["east_west_geometry"]["physical_alignment"] == "horizontal east–west"
    assert result["east_west_geometry"]["receiver_order_sign_known"] is False


def test_frozen_estimator_validation_excludes_discovery_pair() -> None:
    result = json.loads(MODULE_PATH.with_name("results.json").read_text())
    validation = result["frozen_estimator_validation"]

    assert validation["pair_count"] == 11
    assert validation["modeled_boundary_resultant"] > 0.9
    confirmation = validation["confirmation_excluding_exploratory_766_767"]
    assert confirmation["pair_count"] == 10
    assert confirmation["resultant"] > 0.9
    assert confirmation["plus_one_tail_probability"] < 1e-4
