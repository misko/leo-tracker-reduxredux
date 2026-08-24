from __future__ import annotations

import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from tools import report_recent_three_matched_shape_null as report

_ROOT = Path(__file__).parents[2]
_FIGURE_ROOT = _ROOT / "reports/figures/2026_08_24_recent_three_continuity_tle"
_EVIDENCE = _FIGURE_ROOT / "matched-shape-null-evidence.json"
_FIGURE = _FIGURE_ROOT / "matched-shape-null-calibration.png"


def _audit_track(
    label: str,
    path: str,
    rf_hz: float,
    rate_hz_s: float,
    start_s: float,
    end_s: float,
) -> report.AuditTrack:
    selected = SimpleNamespace(
        label=label,
        path=SimpleNamespace(label=path, rf_frequency_hz=rf_hz),
        rate_hz_s=rate_hz_s,
        start_s=start_s,
        end_s=end_s,
        duration_s=end_s - start_s,
    )
    series = report.association.TrackSeries(
        np.asarray([start_s, end_s]),
        np.asarray([0.0, 1.0]),
    )
    return report.AuditTrack(
        selected=selected,
        series=series,
        train=np.asarray([True, False]),
        linear={"holdout_residual_rms_hz": 1.0},
    )


def _sha256(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def test_replica_clusters_use_only_radio_overlap_rf_and_rate() -> None:
    tracks = (
        _audit_track("T1", "stream-0/RX1", 11.0e9, -3_100.0, 2.0, 20.0),
        _audit_track("T2", "stream-1/RX1", 11.0e9 + 2.0, -3_052.0, 5.0, 19.0),
        _audit_track("T3", "stream-1/RX1", 11.1e9, -3_052.0, 5.0, 19.0),
    )

    assert report.replica_clusters(tracks) == ((0, 1), (2,))


def test_westfall_young_minp_uses_inclusive_ranks_and_controls_family() -> None:
    matrix = np.asarray(
        [
            [3.0, 2.0, 1.0],
            [1.0, 2.0, 3.0],
        ]
    )

    result = report.westfall_young_minp(matrix)

    assert result["raw_empirical_p"] == pytest.approx([1.0 / 3.0, 1.0])
    assert result["single_step_minp_fwer_p"] == pytest.approx([2.0 / 3.0, 1.0])
    assert result["step_down_minp_fwer_p"] == pytest.approx([2.0 / 3.0, 1.0])


def test_candidate_selection_never_uses_holdout_ordering() -> None:
    ranked_on_training = [
        {
            "object_name": "training-best",
            "catalog_number": 1,
            "epoch_adjustment_s": 0.0,
            "nuisance_drift_hz_s": 0.0,
            "train_residual_rms_hz": 10.0,
            "holdout_residual_rms_hz": 100.0,
        },
        {
            "object_name": "holdout-best",
            "catalog_number": 2,
            "epoch_adjustment_s": 0.0,
            "nuisance_drift_hz_s": 0.0,
            "train_residual_rms_hz": 12.0,
            "holdout_residual_rms_hz": 80.0,
        },
    ]

    selected = report.finish_selection(ranked_on_training, 200.0)

    assert selected["catalog_number"] == 1
    assert selected["runner_margin_hz"] == pytest.approx(2.0)
    assert selected["heldout_alternative_margin_hz"] == pytest.approx(-20.0)
    assert selected["named_association_statistic"] < 0.0


def test_bound_evidence_reproduces_true_search_and_reports_null_family() -> None:
    evidence = json.loads(_EVIDENCE.read_text(encoding="utf-8"))

    assert evidence["analysis_kind"] == "recent_three_matched_full_shape_time_null"
    shifts = evidence["method"]["time_shifts_s"]
    assert len(shifts) == len(set(shifts)) == 41
    assert shifts.count(0.0) == 1
    assert evidence["true_reproduction_audit"]["all_candidate_ids_equal"] is True
    assert evidence["true_reproduction_audit"]["maximum_absolute_numeric_difference_hz"] == 0.0
    assert evidence["dwell_cluster_membership"] == {
        "cap-20260824T192019-9023840c8e9f": [["T1", "T3"], ["T2"]],
        "cap-20260824T192252-9981b9c27853": [["T1"], ["T2"], ["T3"]],
        "cap-20260824T192531-491832825b97": [["T1", "T2"], ["T3"]],
    }
    line_family = evidence["cluster_all_receiver_line_gain_family"]
    assert min(line_family["raw_empirical_p"]) == pytest.approx(2.0 / 41.0)
    assert min(line_family["single_step_minp_fwer_p"]) == pytest.approx(9.0 / 41.0)
    named_family = evidence["cluster_named_association_family"]
    assert min(named_family["raw_empirical_p"]) == pytest.approx(9.0 / 41.0)
    assert min(named_family["single_step_minp_fwer_p"]) == pytest.approx(34.0 / 41.0)
    population = evidence["population"]
    assert population["cluster_win_count"]["true_value"] == 6.0
    assert population["cluster_win_count"]["empirical_p"] == pytest.approx(10.0 / 41.0)
    assert population["dwell_win_count"]["true_value"] == 3.0
    assert population["dwell_win_count"]["empirical_p"] == pytest.approx(12.0 / 41.0)
    assert population["equal_dwell_mean_all_receiver_log_line_mse_gain"][
        "empirical_p"
    ] == pytest.approx(3.0 / 41.0)
    assert population["equal_dwell_median_all_receiver_log_line_mse_gain"][
        "empirical_p"
    ] == pytest.approx(5.0 / 41.0)
    assert population["runner_100_cluster_count"]["true_value"] == 0.0
    assert population["numerical_gate_cluster_count"]["true_value"] == 0.0


def test_bound_artifact_hashes_and_png_are_current() -> None:
    evidence = json.loads(_EVIDENCE.read_text(encoding="utf-8"))

    assert evidence["tool_sha256"] == _sha256(
        _ROOT / "tools/report_recent_three_matched_shape_null.py"
    )
    assert evidence["source_evidence_sha256"] == _sha256(
        _FIGURE_ROOT / "recent-three-degree1-evidence.json"
    )
    assert evidence["published_evidence_sha256"] == _sha256(
        _FIGURE_ROOT / "recent-three-tle-null-evidence.json"
    )
    assert _FIGURE.read_bytes().startswith(b"\x89PNG\r\n\x1a\n")
    assert _FIGURE.stat().st_size > 100_000
