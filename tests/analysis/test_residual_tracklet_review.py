import importlib.util
import sys
from dataclasses import replace
from pathlib import Path

import numpy as np
import pytest

from leo.analysis.polynomial_tracklets import TrackConfig, _piece, _predict, _wrap
from leo.analysis.residual_tracklets import fit_lane


@pytest.fixture
def review(monkeypatch):
    tools = Path(__file__).resolve().parents[2] / "tools"
    monkeypatch.syspath_prepend(str(tools))
    spec = importlib.util.spec_from_file_location(
        "residual_review", tools / "review_unassociated_tracklets.py"
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_append_freezes_existing_ownership_and_coefficients(review):
    cfg = replace(TrackConfig(), points_per_coefficient=2)
    first = np.linspace(0, 25, 20)
    second = np.linspace(50, 75, 10)
    t = np.r_[first, second]
    y = _wrap(
        np.r_[50000 - 800 * first, 70000 - 1500 * second + 15 * second**2], cfg.alias_spacing_hz
    )
    base = fit_lane(first, y[:20], cfg)
    base["assignment"] = np.r_[base["assignment"], np.full(10, -1)]
    base["alias_lifts"] = np.r_[base["alias_lifts"], np.zeros(10, int)]
    coefficients = base["tracks"][0]["pieces"][0]["coefficients_hz"].copy()
    result = review.append_recovery(base, t, y, cfg, fit_lane, "test")
    assert np.all(result["assignment"][:20] == 0)
    assert np.all(result["assignment"][20:] == 1)
    assert np.all(base["assignment"][20:] == -1)
    assert len(base["tracks"]) == 1
    np.testing.assert_array_equal(coefficients, result["tracks"][0]["pieces"][0]["coefficients_hz"])


def test_append_rejects_structured_residuals_within_the_frequency_gate(review):
    cfg = TrackConfig()
    t = np.arange(40.0)
    y = -800 * t + np.where(t < 20, 100.0, -100.0)
    ix = np.arange(len(t))
    piece = _piece(t, y, ix, 1)
    residual = y - _predict(piece, t)
    assert np.max(abs(residual)) < 450
    rescue = {
        "tracks": [
            {
                "indices": ix,
                "pieces": [piece],
                "residual_rms_hz": float(np.sqrt(np.mean(residual**2))),
            }
        ],
        "assignment": np.zeros(len(t), int),
        "alias_lifts": np.zeros(len(t), int),
    }
    base = {"tracks": [], "assignment": np.full(len(t), -1), "alias_lifts": np.zeros(len(t), int)}
    result = review.append_recovery(base, t, y, cfg, lambda *_: rescue, "test")
    assert not result["tracks"]
    assert np.all(result["assignment"] == -1)
    assert result["diagnostics"]["recovery"][0]["rejected_structured_candidates"]
