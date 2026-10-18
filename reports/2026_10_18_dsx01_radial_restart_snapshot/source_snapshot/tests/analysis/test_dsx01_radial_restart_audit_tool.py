"""Detect cross-start leakage, unmatched controls and incorrect association counts."""

import copy
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))
from audit_dsx01_radial_restarts import (  # noqa: E402
    canonical_starts,
    check_result,
    common_arms,
    digest,
    replay_endpoint_gradients,
)


def discovery_fixture(directory):
    path = directory / "DSX01-S01/discovery/start_00/discovery.json"
    data = dict(
        method="discover", case="DSX01-S01", start_id=0,
        start_east_north_km=[0, 0], status="complete", source_fingerprint="source",
        GPS_or_following_TLE_used=False,
        input_audit=dict(
            cutoff_utc_ns=100, origin_utc_ns=101,
            latest_max_collection_utc_ns=90, latest_max_epoch_utc_ns=80,
            previous_element_byte_epochs_validated=True,
        ),
        actual_report_inputs_read=[],
        discovery_provenance=dict(
            zero_initial_radio_phase_and_smooth=True,
            saved_atlas_labels_calibration_or_site_read=False,
            alias_anchor_east_north_km=[0, 0],
        ),
    )
    return path, data


def test_disk_has_center_twelve_radial_starts_and_four_boundary_points():
    starts = canonical_starts()
    assert len(starts) == 13 and starts[0] == [0, 0] and starts[12] == [10, 0]
    assert sum(e * e + n * n == 100 for e, n in starts) == 4
    assert all(e * e + n * n <= 100 for e, n in starts)


def test_discovery_audit_detects_reading_another_starts_state(tmp_path):
    path, data = discovery_fixture(tmp_path)
    data["actual_report_inputs_read"] = [str(
        tmp_path / "DSX01-S01/discovery/start_12/discovery.json"
    )]
    errors = []
    check_result(data, path, {"source_fingerprint": "source"}, tmp_path, errors)
    assert any("cross-start" in error for error in errors)


def test_discovery_audit_detects_future_collection_even_with_past_element(tmp_path):
    path, data = discovery_fixture(tmp_path)
    data["input_audit"]["latest_max_collection_utc_ns"] = 102
    errors = []
    check_result(data, path, {"source_fingerprint": "source"}, tmp_path, errors)
    assert any("noncausal latest_max_collection" in error for error in errors)


def test_matched_control_audit_checks_alias_labels_and_position_start():
    arm = dict(
        fit=dict(history=[dict(parameters=[0, 0])]),
        aliases=[0], rows=[dict(component="curve", candidate_index=1)], members=[0], labels=[1],
    )
    arms = dict(c0=arm, fitted_c=copy.deepcopy(arm))
    arms["fitted_c"]["aliases"] = [2]
    arms["fitted_c"]["labels"] = [3]
    arms["fitted_c"]["fit"]["history"][0]["parameters"] = [5, 0]
    errors = []
    common_arms(arms, errors, "test")
    assert any("unmatched aliases" in e for e in errors)
    assert any("unmatched labels" in e for e in errors)
    assert any("different starting positions" in e for e in errors)


def test_audit_recomputes_associated_points_and_tracks(tmp_path):
    discovery_path, data = discovery_fixture(tmp_path)
    discovery_path.parent.mkdir(parents=True)
    discovery_path.write_text("discovery bytes")
    path = tmp_path / "DSX01-S01/normal/start_00/result.json"
    arm = dict(
        fit=dict(parameters=[1, 2], history=[dict(parameters=[0, 0])]),
        endpoint_east_north_km=[1, 2], aliases=[0],
        associated_points=7, associated_tracks=2,
        association_metrics=dict(tracks=[dict(points=6, compatible=True)]),
    )
    data.update(
        method="normal", discovery_sha256=digest(discovery_path),
        arms=dict(c0=arm, fitted_c=copy.deepcopy(arm)), rounds=[],
    )
    errors = []
    check_result(data, path, {"source_fingerprint": "source"}, tmp_path, errors)
    assert sum("incorrect associated-point count" in error for error in errors) == 2
    assert sum("incorrect associated-track count" in error for error in errors) == 2


def test_endpoint_replay_reports_nonstationary_gradient_without_refitting(tmp_path, monkeypatch):
    import map_dsx01_clean_region as mapper
    import run_dsx01_clean_region as discovery

    monkeypatch.setattr(discovery, "load_scan", lambda _case: (None, 150.0))
    monkeypatch.setattr(
        mapper, "factory", lambda *_a, **_k: SimpleNamespace(
            residual=lambda x: np.asarray(x) - [1.0, 2.0]
        )
    )
    for start_id in (0, 12):
        path = tmp_path / "DSX01-S01/normal" / f"start_{start_id:02d}" / "result.json"
        path.parent.mkdir(parents=True)
        path.write_text(json.dumps(dict(
            final_node={}, final_reference=None, source_fingerprint="test",
            arms={arm: dict(fit=dict(parameters=[3.0, 4.0], score=8.0))
                  for arm in ("c0", "fitted_c")},
        )))
    result = replay_endpoint_gradients(tmp_path)
    assert result["passed"] and result["complete"]
    assert result["max_absolute_score_difference"] == 0
    for row in result["rows"]:
        np.testing.assert_allclose(row["gradient_loss_per_km"], [4.0, 4.0], atol=1e-10)
        assert row["derivative_step_km"] == 0.05
