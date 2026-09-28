import importlib.util
import json
from pathlib import Path

import numpy as np
import pytest

PATH = Path(__file__).parents[2] / "tools" / "ds7_baseline_adapter.py"
SPEC = importlib.util.spec_from_file_location("ds7_baseline_adapter", PATH)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def test_stationary_profiler_finds_nontrivial_mode():
    values = np.array([-1000.0] * 8 + [1000.0] * 3)
    offset, audit = MODULE.fit_stationary_offset(values)
    assert audit["converged"]
    assert audit["roots"] >= 1
    assert offset < -900


def test_site_returns_wgs84_ecef_and_unit_up():
    rec, up = MODULE.site(0.0, 0.0)
    np.testing.assert_allclose(rec, [6378.137, 0, 0], atol=1e-9)
    np.testing.assert_allclose(up, [1, 0, 0], atol=1e-12)


def test_stationary_envelope_gradient_matches_full_objective_difference():
    times = np.array([0.0, 1.0, 2.0, 3.0])
    taus = np.array([-0.25, 0.0, 0.25])
    candidates = 2
    positions = np.empty((candidates, len(taus), len(times), 3))
    velocities = np.empty_like(positions)
    receiver, up = MODULE.site(37.85625, -122.484375)
    for candidate in range(candidates):
        for index, tau in enumerate(taus):
            positions[candidate, index] = (
                receiver + up * 1000 + np.column_stack((np.zeros(4), times * 2 + tau, np.zeros(4)))
            )
            velocities[candidate, index] = np.array([[-0.2, 7.4 + candidate * 0.01, 0.1]] * 4)
    track = {
        "candidate_position_km": positions,
        "candidate_velocity_km_s": velocities,
        "mask": np.array([True, True, True, False]),
        "y": np.array([-180000.0, -180020.0, -180050.0, -180070.0]),
        "catalogue_size": 100,
    }
    model = MODULE.Stationary(
        {"tracks": [track]},
        {"geographic_prior_center_deg": [37.85625, -122.484375], "timing_grid_s": taus},
    )
    point = np.array([0.2, -0.1, 0.0])
    _, analytic = model.evaluate(point, True)
    numeric = []
    for axis in range(3):
        step = 1e-4
        plus, minus = point.copy(), point.copy()
        plus[axis] += step
        minus[axis] -= step
        numeric.append((model.evaluate(plus)[0] - model.evaluate(minus)[0]) / (2 * step))
    np.testing.assert_allclose(analytic, numeric, rtol=2e-3, atol=2e-3)


def test_loader_rejects_candidate_bank_bound_to_other_observation_bytes(tmp_path):
    observations = tmp_path / "observations.json"
    observations.write_text(
        json.dumps(
            {
                "schema": "ds7-baseline-track-export/v1",
                "session_id": "scan-fw-example",
                "manifest_sha256": "sha256:source",
                "tracks": [],
            }
        )
    )
    manifest = tmp_path / "manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "session_id": "scan-fw-example",
                "manifest_sha256": "sha256:source",
                "tracks_sha256": "sha256:wrong",
                "tracks": [],
            }
        )
    )
    np.savez(tmp_path / "banks.npz", timing_grid_s=np.array([-5.0, 5.0]))
    request = {
        "config": {"timing_grid_s": [-5.0, 5.0]},
        "inputs": [
            {
                "session_id": "scan-fw-example",
                "manifest_sha256": "sha256:source",
                "artifacts": [
                    {"kind": "observations", "path": str(observations)},
                    {"kind": "candidates", "path": str(manifest)},
                    {"kind": "candidates", "path": str(tmp_path / "banks.npz")},
                ],
            }
        ],
    }
    with pytest.raises(ValueError, match="does not bind"):
        MODULE.load_documents(request)
