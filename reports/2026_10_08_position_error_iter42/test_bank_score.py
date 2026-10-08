from types import SimpleNamespace

import numpy as np
from bank_score import score_bank

from leo.analysis.hard60_score import likelihood


def test_matches_native_and_alias_invariance():
    rng = np.random.default_rng(42)
    measured = rng.normal(0, 1000, 80)
    prediction = measured[:, None] + rng.normal(0, 500, (80, 9))
    visible = rng.random((80, 9)) > 0.2
    score = SimpleNamespace(detection_budget=1.2, sigma_hz=125, clutter_rate=0.1)
    expected = likelihood(measured, prediction, visible, score)
    actual = score_bank(measured, prediction, visible, score)
    np.testing.assert_allclose(actual["nll"], expected.nll, atol=1e-10, rtol=0)
    np.testing.assert_allclose(actual["signal_mass"], expected.responsibilities.sum(), atol=1e-10)
    shifted = score_bank(measured + 1 / 4.4e-6, prediction, visible, score)
    np.testing.assert_allclose(shifted["nll"], actual["nll"], atol=1e-9, rtol=0)


def test_extra_invisible_columns_only_change_normalization():
    score = SimpleNamespace(detection_budget=1, sigma_hz=125, clutter_rate=0.1)
    measured = np.array([0.0, 500.0])
    prediction = np.zeros((2, 4))
    visible = np.ones((2, 4), dtype=bool)
    normalized = score_bank(measured, prediction, visible, score, 8)
    expanded = score_bank(
        measured,
        np.column_stack([prediction, prediction]),
        np.column_stack([visible, np.zeros_like(visible)]),
        score,
    )
    assert normalized == expanded
