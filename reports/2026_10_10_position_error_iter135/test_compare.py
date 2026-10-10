import copy
import runpy
from pathlib import Path

import numpy as np
import pytest
from compare import compare

REPORTS = Path(__file__).resolve().parent.parent


def fixture():
    api = runpy.run_path(str(REPORTS / "2026_10_10_position_error_iter133/test_compare.py"))
    model, archive, _ = api["fixture"]()
    return model, archive


def test_four_calls_same_start_locks_priors_original_measurements_and_failure():
    model, archive = fixture()
    original_vector = archive["stages"]["B7"]["fitted-c"]["vector"].copy()
    # Distinguish c0 archived seed to prove it is NOT used to start c0 fits.
    zero = archive["stages"]["B7"]["zero-c"]
    zero["vector"] = zero["vector"].copy()
    zero["vector"][0] += 1
    zero["objective"] = model.evaluate_joint(zero["vector"], zero["clock_coefficients"])[0]
    calls = []

    def fit(candidate, vector, clock, arm):
        calls.append((type(candidate).__name__, vector.copy(), clock.copy(), arm))
        np.testing.assert_array_equal(
            candidate.observations.measured_hz, model.observations.measured_hz
        )
        np.testing.assert_array_equal(candidate.precision, model.precision)
        assert not np.shares_memory(candidate.precision, model.precision)
        vector[:] = 999
        clock[:] = 999
        if len(calls) == 3:
            raise ValueError("explicit failed phase fit")
        return dict(converged=True)

    result = compare(model, archive, fit)
    assert len(calls) == 4 and result["status"] == "attempt-failed"
    assert [row[0] for row in calls] == [
        "SlopePrior",
        "SlopePrior",
        "PhaseObjective",
        "PhaseObjective",
    ]
    for _, vector, clock, arm in calls:
        expected = original_vector.copy()
        if arm == "zero-c":
            expected[6] = 0
            assert np.all(clock[-2:] == 0)
        np.testing.assert_array_equal(vector, expected)
    assert result["attempts"]["phase"]["zero-c"]["qualified"]


def test_control_parity_blocks_before_every_fit():
    model, archive = fixture()
    archive["stages"]["B7"]["zero-c"]["objective"] += 1
    with pytest.raises(ValueError, match="archived objective"):
        compare(model, archive, lambda *args: pytest.fail("must not fit"))


def test_reference_poison_does_not_change_starts_or_model_evaluations():
    clean = runpy.run_path(str(REPORTS / "2026_10_10_position_error_iter132/test_reconstruct.py"))
    clean["test_reference_perturbations_do_not_change_inference_projection"]()
    model, archive = fixture()
    changed = copy.deepcopy(archive)
    changed["reference_latitude_deg"] = "POISON"
    for saved in changed["stages"]["B7"].values():
        saved["horizontal_error_km"] = "POISON"
    traces = []

    def fit(candidate, vector, clock, arm):
        traces.append(
            (arm, vector.copy(), clock.copy(), candidate.evaluate_joint(vector, clock)[0])
        )
        return dict(converged=True)

    compare(model, archive, fit)
    compare(model, changed, fit)
    for a, b in zip(traces[:4], traces[4:], strict=True):
        assert a[0] == b[0] and a[3] == b[3]
        np.testing.assert_array_equal(a[1], b[1])
        np.testing.assert_array_equal(a[2], b[2])


def test_immutable_phase_all_gradients_and_zero_relative_equivalence():
    tests = runpy.run_path(str(REPORTS / "2026_10_10_position_error_iter130/test_objective.py"))
    tests["test_all_spatial_timing_clock_satellite_gradients"]()
    tests["test_zero_relative_score_and_clock_parity_but_relative_derivative_changes"]()
