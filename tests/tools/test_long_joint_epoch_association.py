import importlib.util
from pathlib import Path

import numpy as np
import pytest


def modules():
    root = Path(__file__).parents[2]
    spec = importlib.util.spec_from_file_location(
        "joint_epoch", root / "reports/2026_09_23_long_joint_epoch_association/refine.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    single = module.load(root / "reports/2026_09_23_long_training_search/search.py", "single")
    return module, single


def synthetic(single):
    grid = np.arange(-5, 12, dtype=float)
    positions = np.tile([7000.0, 0.0, 0.0], (2, len(grid), 1))
    velocities = np.zeros_like(positions)
    velocities[0, :, 0] = 0.02 * grid**2
    velocities[1, :, 0] = 0.06 * grid**2
    arrays = {
        "position_ecef_km": positions,
        "velocity_ecef_km_s": velocities,
        "receive_plus_tau_offset_ns": (grid * 1e9).astype(np.int64),
        "candidate_id": np.array(["one", "two"]),
    }
    times = np.arange(6, dtype=float)
    _, vel = single.interpolate_track(
        positions, velocities, arrays["receive_plus_tau_offset_ns"], times + 0.37
    )
    measured = -single.REFERENCE_RF_HZ / single.LIGHT_KM_S * vel[1, :, 0] + 12345.0
    evidence = [
        {
            "track_id": "track",
            "times_s": times.tolist(),
            "measured_hz": measured.tolist(),
            "training_mask": [True, False, True, False, True, False],
        }
    ]
    return arrays, evidence


def test_fractional_scan_epoch_assignment_ignores_held_frequency():
    module, single = modules()
    arrays, evidence = synthetic(single)
    tracks, rows = module.select_scan(single, arrays, evidence, (0.0, 0.0), 0.37)
    assert rows[0]["candidate_id"] == "two"
    assert rows[0]["training_rms_hz"] < 1e-9
    assert rows[0]["frequency_offset_hz"] == pytest.approx(12345.0)
    for index in (1, 3, 5):
        evidence[0]["measured_hz"][index] += 1e8
    changed_tracks, changed_rows = module.select_scan(single, arrays, evidence, (0.0, 0.0), 0.37)
    assert changed_rows == rows
    assert changed_tracks[0]["candidate_id"] == tracks[0]["candidate_id"]
    np.testing.assert_array_equal(tracks[0]["position"], arrays["position_ecef_km"][1])
    assert not np.shares_memory(tracks[0]["position"], arrays["position_ecef_km"])


def test_no_visible_candidate_fails_without_dropping_support():
    module, single = modules()
    arrays, evidence = synthetic(single)
    arrays["position_ecef_km"] *= -1
    with pytest.raises(ValueError, match="no visible candidate"):
        module.select_scan(single, arrays, evidence, (0.0, 0.0), 0.37)


def test_outer_termination_does_not_call_cycle_limit_stable():
    module, _ = modules()
    assert module.outer_stop_reason(1, 0, 0.0001) == "stable_identities_small_gain"
    assert module.outer_stop_reason(1, 2, 0.0001) is None
    assert module.outer_stop_reason(3, 2, 0.0001) is None
    assert module.outer_stop_reason(10, 2, 0.0001) == "cycle_limit"
    assert module.outer_stop_reason(10, 0, 0.1) == "cycle_limit"


def test_evaluation_rejects_changed_bound_protocol(tmp_path, monkeypatch):
    root = Path(__file__).parents[2] / "reports/2026_09_23_long_joint_epoch_association"
    monkeypatch.syspath_prepend(str(root))
    module, _ = modules()
    evaluator = module.load(root / "evaluate.py", "joint_evaluate")
    paths = [tmp_path / name for name in ("helper", "single", "tool", "protocol")]
    for path in paths:
        path.write_text(path.name)
    source = {"bindings": {path.name: module.digest(path) for path in paths}}
    evaluator.verify_sources(source, *paths)
    paths[-1].write_text("changed after seal")
    with pytest.raises(ValueError, match="bound protocol source changed"):
        evaluator.verify_sources(source, *paths)
