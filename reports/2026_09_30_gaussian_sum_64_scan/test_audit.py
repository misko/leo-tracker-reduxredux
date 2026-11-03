from __future__ import annotations

import hashlib
import json
from pathlib import Path

from audit import ARMS, SPATIAL_PRIOR, audit_panel


def _digest(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _write(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")


def _panel(root: Path) -> None:
    unit = "DS9-F001"
    evidence = root / "inputs" / f"{unit}.json"
    orbit_meta = root / "inputs" / f"{unit}-orbits.json"
    orbit_state = root / "inputs" / f"{unit}-orbits.npz"
    source = root / "source.json"
    code = root / "frozen-physics.py"
    orbit_state.parent.mkdir(parents=True)
    code.write_text("# frozen\n", encoding="utf-8")
    source.write_text("{}", encoding="utf-8")
    orbit_state.write_bytes(b"orbit")
    tracks = [
        {
            "track_id": "first",
            "support_start_utc_ns": 1,
            "support_end_utc_ns": 5,
            "measured_hz": [1, 2, 3],
            "physical_observation_ids": ["a", "b", "c"],
        },
        {
            "track_id": "overlap",
            "support_start_utc_ns": 2,
            "support_end_utc_ns": 6,
            "measured_hz": [2, 3, 4],
            "physical_observation_ids": ["c", "d", "e"],
        },
    ]
    _write(evidence, {"tracks": tracks})
    _write(orbit_meta, {"state": "bound"})
    initial = 32 * [
        {
            "weight": 1.0 / 32,
            "mean": [0, 0, 0, 0, 0, 0],
            "covariance": [[1, 0], [0, 1]],
            "identity_history": [],
        }
    ]
    exclusion = [
        {
            "track_id": "overlap",
            "reason": "same_receiver_source_overlap",
            "conflicting_ids": ["c"],
        }
    ]
    for arm in ARMS:
        config = {
            "physics": {
                "reference_frequency_hz": 11.2e9,
                "prior_center_lat_deg": 38.5816,
                "prior_center_lon_deg": -121.4944,
                "support_radius_km": 489.0,
            },
            "filter": {
                "max_components": 32,
                "min_weight": 1e-12,
                "greedy": arm == "greedy",
                "max_child_work": 65536,
            },
            "prior": "sacramento_uniform",
            "spatial_prior": dict(SPATIAL_PRIOR),
        }
        prediction = root / "runs" / "batch-01" / f"{unit}-sacramento_uniform-{arm}.json"
        state = prediction.with_suffix(".state.npz")
        state.parent.mkdir(parents=True, exist_ok=True)
        state.write_bytes(arm.encode())
        checkpoints = []
        final = initial
        if arm != "prior_only":
            final = [{**initial[0], "identity_history": ["sat"]}]
            checkpoints = [
                {
                    "factor": 0,
                    "track_id": "first",
                    "elapsed_support_s": 1.0,
                    "consumed_samples": 3,
                    "components": final,
                }
            ]
        receipt = {
            "schema": "gaussian-sum-single-scan-prediction/v1",
            "unit_id": unit,
            "arm": arm,
            "prior_name": "sacramento_uniform",
            "status": "complete",
            "config": config,
            "config_sha256": "sha256:"
            + hashlib.sha256(json.dumps(config, sort_keys=True).encode()).hexdigest(),
            "source_sha256": {str(code): _digest(code)},
            "inputs": {
                str(evidence): _digest(evidence),
                str(orbit_meta): _digest(orbit_meta),
                str(orbit_state): _digest(orbit_state),
            },
            "state_artifact": {"path": str(state), "sha256": _digest(state)},
            "selection": {"all_tracks": 2, "retained_tracks": 1, "exclusions": exclusion},
            "initial_components": initial,
            "state_dimension": 1000,
            "initial_state_summary": {
                "component_count": 32,
                "state_dimension": 1000,
                "weight_sum": 1.0,
                "histories_empty": True,
                "max_abs_tau_s": 0.0,
                "max_abs_rx_drift_hz_s": 0.0,
                "max_abs_satellite_epoch_s": 0.0,
            },
            "components": final,
            "checkpoints": checkpoints,
            "prior_point_estimate": {
                "latitude_deg": 38.5816,
                "longitude_deg": -121.4944,
                "rule": "center_of_intended_uniform_disk",
            },
        }
        _write(prediction, receipt)
        _write(prediction.with_suffix(".seal.json"), {"prediction_sha256": _digest(prediction)})
        launch = {
            "unit_id": unit,
            "arm": arm,
            "status": "complete",
            "prediction_path": str(prediction),
            "native_status": "complete",
        }
        _write(prediction.with_suffix(".launch.json"), launch)


def test_complete_panel_passes_all_binding_and_reset_checks(tmp_path: Path) -> None:
    _panel(tmp_path)
    result = audit_panel(tmp_path, ["DS9-F001"])
    assert result.valid, result.issues
    assert result.expected_attempts == result.launch_receipts == result.native_receipts == 3
    assert result.native_status_counts == {"complete": 3}


def test_detects_tampered_seal_overlap_and_prior_reset(tmp_path: Path) -> None:
    _panel(tmp_path)
    prediction = tmp_path / "runs/batch-01/DS9-F001-sacramento_uniform-gaussian_sum.json"
    receipt = json.loads(prediction.read_text())
    receipt["selection"]["exclusions"] = []
    receipt["initial_components"][0]["mean"][3] = 4
    receipt["initial_state_summary"]["max_abs_satellite_epoch_s"] = 0.25
    _write(prediction, receipt)

    result = audit_panel(tmp_path, ["DS9-F001"])
    assert not result.valid
    assert any("seal does not bind" in issue for issue in result.issues)
    assert any("selection mismatch" in issue for issue in result.issues)
    assert any("initial prior differs" in issue for issue in result.issues)
    assert any("nonzero initial nuisance" in issue for issue in result.issues)


def test_missing_attempt_and_nonterminal_launch_are_reported(tmp_path: Path) -> None:
    _panel(tmp_path)
    launch = tmp_path / "runs/batch-01/DS9-F001-sacramento_uniform-greedy.launch.json"
    launch.unlink()
    other = tmp_path / "runs/batch-01/DS9-F001-sacramento_uniform-prior_only.launch.json"
    value = json.loads(other.read_text())
    value["status"] = "running"
    _write(other, value)

    result = audit_panel(tmp_path, ["DS9-F001"])
    assert not result.valid
    assert any("missing launch receipt" in issue for issue in result.issues)
    assert any("nonterminal launch status" in issue for issue in result.issues)
