import importlib.util
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
PATH = ROOT / "reports/2026_09_23_train_receiver_orbit_diagnostic/analyze.py"
SPEC = importlib.util.spec_from_file_location("train_receiver_orbit_diagnostic", PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


def test_nearest_pairs_are_one_to_one_and_respect_tolerance():
    left = np.array([0, 100_000_000, 200_000_000])
    right = np.array([30_000_000, 170_000_000, 400_000_000])
    assert MODULE.nearest_pairs(left, right, 80) == [
        (0, 0, 30_000_000),
        (2, 1, 30_000_000),
    ]


def test_polynomial_terms_recovers_centered_slope_and_quadratic():
    times = np.linspace(1000, 1020, 41)
    centered = times - times.mean()
    values = 938.0 + 3.25 * centered - 0.7 * centered**2
    slope, quadratic = MODULE.polynomial_terms(times, values)
    np.testing.assert_allclose(slope, 3.25, atol=1e-12)
    np.testing.assert_allclose(quadratic, -0.7, atol=1e-12)


def test_group_bootstrap_does_not_treat_rows_as_independent():
    rows = [
        {"group": "a", "value": 0.0},
        {"group": "a", "value": 0.0},
        {"group": "b", "value": 10.0},
    ]
    result = MODULE.summarize(rows, "value", ["a", "b"], bootstrap_count=200)
    assert result["group_count"] == 2
    assert result["pair_count"] == 3
    assert result["ci95"][0] == 0.0
    assert result["ci95"][1] == 10.0
