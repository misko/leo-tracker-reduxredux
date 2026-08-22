from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import numpy as np

_PATH = Path(__file__).parents[2] / "tools" / "report_t1_dense_degree1_only.py"
_SPEC = importlib.util.spec_from_file_location("t1_dense_degree1_only", _PATH)
assert _SPEC and _SPEC.loader
_MODULE = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = _MODULE
_SPEC.loader.exec_module(_MODULE)


def test_huber_line_resists_one_extreme_outlier() -> None:
    times = np.arange(20, dtype=float)
    frequency = 42_000.0 - 5_500.0 * times
    frequency[8] += 500_000.0
    slope, intercept, weights = _MODULE.huber_line(times, frequency)

    assert abs(slope + 5_500.0) < 1.0
    assert abs(intercept - 42_000.0) < 10.0
    assert weights[8] < 0.01


def test_candidate_line_uses_one_candidate_per_probe_and_two_coefficients() -> None:
    candidates = []
    for index, time_s in enumerate(np.arange(0.0, 4.0, 0.1)):
        candidates.extend(
            (
                _MODULE.Candidate(
                    time_s,
                    index,
                    0,
                    10_000.0 - 4_000.0 * time_s,
                    0.3,
                    0.4,
                    0.1,
                ),
                _MODULE.Candidate(
                    time_s,
                    index,
                    1,
                    200_000.0 + 8_000.0 * time_s,
                    0.2,
                    0.3,
                    0.1,
                ),
            )
        )
    grouped = _MODULE.group_candidates(candidates)
    fitted = _MODULE.fit_candidate_line(grouped, 0.0, 4.0, trials=2_000, seed=4)

    assert abs(fitted.slope_hz_s + 4_000.0) < 1.0
    assert abs(fitted.intercept_hz - 10_000.0) < 1.0
    assert fitted.support_count == 40
    assert len({item.time_s for item in fitted.selected}) == fitted.support_count
