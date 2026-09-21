import importlib.util
import json
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[2]


def _load(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "tools" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_predeclared_folds_are_deterministic_and_key_sensitive(monkeypatch):
    monkeypatch.syspath_prepend(str(ROOT / "tools"))
    module = _load("benchmark_position_weighting")
    keys = np.array([[1, 10], [1, 10], [1, 11], [2, 10]])
    first = module._fold("pass", keys)
    np.testing.assert_array_equal(first, module._fold("pass", keys))
    assert first[0] == first[1]
    assert np.all((first >= 0) & (first < module.DELETION_FOLDS))
    assert not np.array_equal(first, module._fold("satellite", keys))


def test_cluster_covariance_detects_common_cluster_error(monkeypatch):
    monkeypatch.syspath_prepend(str(ROOT / "tools"))
    module = _load("benchmark_position_weighting")
    x = np.linspace(-1, 1, 40)
    jacobian = np.column_stack([np.ones(40), x])
    groups = np.repeat(np.arange(8), 5)
    residual = np.repeat(np.array([-4, -3, -2, -1, 1, 2, 3, 4.0]), 5)
    clustered = module._cluster_covariance(jacobian, residual, groups)
    iid = np.sum(residual**2) / (len(residual) - 2) * np.linalg.inv(jacobian.T @ jacobian)
    assert clustered[0, 0] > iid[0, 0]
    np.testing.assert_allclose(clustered, clustered.T)


def test_distance_uses_published_spherical_convention():
    module = _load("evaluate_uncertain_position")
    assert module.distance_m(0, 0, 0, 0) == 0
    assert module.distance_m(0, 1, 0, 0) == pytest.approx(2 * np.pi * module.EARTH_RADIUS_M / 360)


def test_generic_inference_needs_explicit_causal_provenance(tmp_path):
    module = _load("evaluate_uncertain_position")
    path = tmp_path / "result.json"
    path.write_text(json.dumps({"models": [{"latitude_deg": 1, "longitude_deg": 2}]}))
    result = module.evaluate_inference("generic", path, (1, 2))
    assert result["models"][0]["causal_comparison_eligible"] is None
    assert "does not explicitly establish" in result["models"][0]["comparison_exclusion_reason"]


def test_labelled_future_oracle_is_excluded_from_strict_causal_comparison(tmp_path):
    module = _load("evaluate_uncertain_position")
    path = tmp_path / "causal.json"
    path.write_text(
        json.dumps(
            {
                "strictly_causal": True,
                "future_tles_used_for_labelled_diagnostic_only": True,
                "models": [
                    {
                        "orbit_model": "baseline",
                        "latitude_deg": 1,
                        "longitude_deg": 2,
                    },
                    {
                        "orbit_model": "future_tle_oracle_phase",
                        "latitude_deg": 1,
                        "longitude_deg": 2,
                    },
                ],
            }
        )
    )
    models = module.evaluate_inference("causal", path, (1, 2))["models"]
    assert models[0]["causal_comparison_eligible"] is True
    assert models[1]["causal_comparison_eligible"] is False
