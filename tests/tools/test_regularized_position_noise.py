import importlib.util
import sys
from pathlib import Path

import numpy as np

from leo.analysis.adaptive_tle_position import AdaptiveTrackPrediction

PATH = Path(__file__).parents[2] / "tools" / "research" / "audit_regularized_position_noise.py"
SPEC = importlib.util.spec_from_file_location("test_regularized_position_noise_subject", PATH)
assert SPEC.loader is not None
SUBJECT = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = SUBJECT
SPEC.loader.exec_module(SUBJECT)


def _prediction(measured, visible=True):
    measured = np.asarray(measured, dtype=float)
    base = np.arange(len(measured), dtype=float)
    predictions = np.stack(
        [np.stack((base[::-1], base, base**1.2)),
         np.stack((base * .2, base * .5, base * .8))]
    )
    return AdaptiveTrackPrediction(
        "track", tuple(f"o{i}" for i in range(len(base))), base, measured,
        np.asarray([True, False, True, False, True, False, True, False]),
        np.asarray(["10", "20"]), np.asarray([-1., 0., 1.]), predictions,
        np.full(2, visible, dtype=bool),
    )


def test_selection_and_residuals_are_invariant_to_evaluation_frequency_mutation():
    measured = np.arange(8, dtype=float) + 500
    original = _prediction(measured)
    changed = measured.copy()
    changed[~original.training_mask] = [1e9, -2e9, 3e9, -4e9]
    before, after = SUBJECT._select(original), SUBJECT._select(_prediction(changed))
    assert before["candidate_id"] == after["candidate_id"]
    assert before["tau_s"] == after["tau_s"]
    np.testing.assert_allclose(before["residual_hz"], after["residual_hz"])


def test_all_invisible_candidates_are_unmatched():
    assert SUBJECT._select(_prediction(np.arange(8), visible=False)) is None


def test_quantile_summary_has_fixed_ordered_statistics():
    assert SUBJECT._quantiles([1, 2, 3, 4, 5]) == {
        "min": 1.0, "p25": 2.0, "median": 3.0, "p75": 4.0, "max": 5.0
    }
