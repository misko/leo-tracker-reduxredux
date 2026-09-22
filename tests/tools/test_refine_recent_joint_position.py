import importlib.util
import json
from pathlib import Path

import numpy as np
import pytest

from leo.analysis.research.regional_doppler import ObservationArc, Region, ScoreConfig, score_states


def module():
    path = Path(__file__).parents[2] / "tools/research/refine_recent_joint_position.py"
    spec = importlib.util.spec_from_file_location("refine_recent_joint_position", path)
    loaded = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(loaded)
    return loaded


def test_refinement_compares_modes_with_identity_refreshing_score():
    seen = []

    def score(point):
        seen.append(tuple(point))
        # Two candidate/location explanations. The best identity changes in space.
        return max(-np.sum((point - [25, 5]) ** 2), 10 - np.sum((point - [-25, -5]) ** 2))

    fits = module().refine_modes(score, [[20, 0], [-20, 0]], Region(0, 0, 100, 100))
    best = max(fits, key=lambda fit: fit["training_score"])
    assert best["converged"]
    assert best["east_km"] == pytest.approx(-25, abs=0.02)
    assert best["north_km"] == pytest.approx(-5, abs=0.02)
    assert any(x > 0 for x, y in seen) and any(x < 0 for x, y in seen)


def test_identity_probabilities_keep_full_catalogue_prior_and_ignore_heldout_values():
    arc = ObservationArc(
        np.arange(4.0),
        np.array([1.0, 2.0, 3.0, 4.0]),
        np.zeros(4),
        np.array([True, True, False, False]),
    )
    grid = Region(0, 0, 100, 100).points([0], [0])
    p = np.tile(grid.ecef_km[0] + [500, 0, 0], (2, 4, 1))
    v = np.zeros_like(p)
    runner = module()
    weights, null = runner.posterior_at(arc, p, v, grid, 11000, ScoreConfig())
    assert np.sum(weights) + null == pytest.approx(1)
    assert weights[0] == pytest.approx(weights[1])
    acquisition_score = score_states(arc, p, v, grid, 11000, ScoreConfig())
    assert np.sum(weights) == pytest.approx(acquisition_score["signal_weight"][0])
    poisoned = ObservationArc(
        arc.time_s, np.array([1.0, 2.0, 1e9, -1e9]), arc.segment, arc.training
    )
    changed, changed_null = runner.posterior_at(poisoned, p, v, grid, 11000, ScoreConfig())
    np.testing.assert_array_equal(changed, weights)
    assert changed_null == null
    _, smaller_null = runner.posterior_at(arc, p, v, grid, 2, ScoreConfig())
    assert null > smaller_null


def test_invisible_candidates_preserve_null_assignment():
    arc = ObservationArc(
        np.arange(4.0), np.arange(4.0), np.zeros(4), np.array([True, True, False, False])
    )
    grid = Region(0, 0, 100, 100).points([0], [0])
    p = np.tile(-grid.ecef_km[0], (2, 4, 1))
    weights, null = module().posterior_at(arc, p, np.zeros_like(p), grid, 11000, ScoreConfig())
    np.testing.assert_array_equal(weights, [0, 0])
    assert null == 1


def sealed_acquisition(path, **overrides):
    runner = module()
    result = dict(scan_count=1, clock_s=0, altitude_m=0)
    result.update(overrides)
    files = {
        "result.json": json.dumps(result),
        "configuration.json": "{}",
        "history.json": '[{"session_id":"a"}]',
        "grid.npz": "grid",
        "accumulated.npz": "scores",
        "a.npz": "scan-scores",
    }
    for name, payload in files.items():
        (path / name).write_text(payload)
    (path / "acquisition-seal.json").write_text(
        json.dumps({"files": {name: runner.digest(path / name) for name in files}})
    )
    return runner


def test_coarse_seed_tampering_is_rejected(tmp_path):
    runner = sealed_acquisition(tmp_path)
    runner.verify_acquisition(tmp_path)
    (tmp_path / "grid.npz").write_text("different-seed-grid")
    with pytest.raises(ValueError, match="seal mismatch"):
        runner.verify_acquisition(tmp_path)


@pytest.mark.parametrize("overrides", [{"clock_s": 1}, {"altitude_m": 1}, {"scan_count": 2}])
def test_incompatible_acquisition_configuration_is_rejected(tmp_path, overrides):
    runner = sealed_acquisition(tmp_path, **overrides)
    with pytest.raises(ValueError):
        runner.verify_acquisition(tmp_path)
