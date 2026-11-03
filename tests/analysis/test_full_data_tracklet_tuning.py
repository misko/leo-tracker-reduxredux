import importlib.util
import sys
from pathlib import Path

import numpy as np
import pytest


@pytest.fixture
def tuning(monkeypatch):
    tools = Path(__file__).resolve().parents[2] / "tools"
    monkeypatch.syspath_prepend(str(tools))
    spec = importlib.util.spec_from_file_location(
        "tune_full_data", tools / "tune_full_data_tracklets.py"
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_zero_mean_structured_residuals_fail(tuning):
    t = np.arange(80.0)
    r = np.r_[np.full(40, -100.0), np.full(40, 100.0)]
    result = tuning.full_residual_diagnostics(t, r)
    assert result["mean_hz"] == 0
    assert result["status"] == "structure_flagged"
    assert "adjacent_residual_correlation" in result["flags"]
    assert "residual_mean_step" in result["flags"]


def test_white_noise_passes_and_short_support_is_provisional(tuning):
    rng = np.random.default_rng(987)
    result = tuning.full_residual_diagnostics(np.arange(200.0), rng.normal(0, 100, 200))
    assert result["status"] == "no_structure_detected"
    short = tuning.full_residual_diagnostics(np.arange(12.0), rng.normal(0, 50, 12))
    assert short["status"] == "insufficient_support"


def test_ranking_prioritizes_supported_structure_free_associations(tuning):
    def summary(clean, assigned):
        return {
            "assigned": assigned,
            "track_count": 10,
            "residual_quality": {
                "no_structure_detected": {"associated_points": clean},
                "structure_flagged": {"associated_points": 0},
            },
            "residual_diagnostics": {"rms_hz": 100},
        }

    assert tuning.rank_candidate(summary(80, 90)) > tuning.rank_candidate(summary(70, 100))
    assert tuning.rank_candidate(summary(80, 95)) > tuning.rank_candidate(summary(80, 90))
