"""Phase-only diagnostic search stays bounded and fits no receiver parameters."""

import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))
from probe_dsx01_late_family import phase_search  # noqa: E402


@pytest.mark.parametrize("truth", [-2.3, 4.5])
def test_phase_search_matches_independent_quadratic_optimum(truth):
    queries = []

    def objective(phase):
        queries.append(phase)
        return (phase - truth) ** 2 + 7

    phase, score = phase_search(objective)
    assert phase == pytest.approx(truth, abs=1e-6)
    assert score == pytest.approx(7, abs=1e-12)
    assert np.all(np.abs(queries) <= 15.0)
