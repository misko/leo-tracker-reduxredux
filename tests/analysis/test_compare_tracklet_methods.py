import importlib.util
import sys
from pathlib import Path

import numpy as np
import pytest

from leo.analysis.polynomial_tracklets import TrackConfig, _piece
from leo.analysis.tracklet_fitting import finish_lane, prepare_lane

TOOLS = Path(__file__).resolve().parents[2] / "tools"


@pytest.fixture
def comparison(monkeypatch):
    monkeypatch.syspath_prepend(str(TOOLS))
    spec = importlib.util.spec_from_file_location(
        "compare_methods", TOOLS / "compare_tracklet_methods.py"
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_independent_audit_rejects_duplicate_ownership(comparison):
    t, y, order, n = prepare_lane(np.linspace(0, 30, 61), np.linspace(0, 15_000, 61))
    cfg = TrackConfig()
    result = finish_lane(t, y, order, n, [_piece(t, y, np.arange(n), 1)], cfg, "test")
    comparison.assert_integrity(result, t, y, cfg)
    result["tracks"].append(result["tracks"][0])
    with pytest.raises(AssertionError):
        comparison.assert_integrity(result, t, y, cfg)


def test_synthetic_benchmark_keeps_every_signal_and_clutter_denominator(comparison):
    def reject_everything(t, y, config):
        return {
            "tracks": [],
            "assignment": -np.ones(len(t), int),
            "alias_lifts": np.zeros(len(t), int),
        }

    cases = comparison.synthetic_benchmark(reject_everything, TrackConfig())
    crossing = next(c for c in cases if c["case"] == "crossing_and_clutter")
    assert crossing["observations"] == 462
    assert crossing["clutter_observations"] == 100
    assert crossing["signal_coverage"] == 0
    assert all(c["assigned"] == 0 for c in cases)
