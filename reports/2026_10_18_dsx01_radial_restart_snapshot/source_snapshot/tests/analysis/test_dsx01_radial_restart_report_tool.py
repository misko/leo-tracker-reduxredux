"""Scientific plotting semantics for independent-start association experiments."""

import json
import sys
from pathlib import Path

import numpy as np
from matplotlib.figure import Figure

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))
from report_dsx01_radial_restarts import (  # noqa: E402
    annotate_start,
    assignment_difference,
    compact_record,
    endpoint_groups,
    raw_denominators,
    round_trajectories,
    run,
    summarize,
    trajectory,
)


def test_start_labels_show_coordinates_and_pending_status():
    figure = Figure()
    axis = figure.subplots()
    annotate_start(axis, 12, [10, 0])
    annotate_start(axis, "start_07", [-5, 5], pending=True)
    assert axis.texts[0].get_text() == "S12\n(+10, +0) km"
    assert axis.texts[0].xy == (10, 0)
    assert axis.texts[1].get_text() == "S07 pending\n(-5, +5) km"
    assert axis.texts[1].get_color() != axis.texts[0].get_color()


def arm(point, score):
    return dict(
        fit=dict(parameters=point, score=score, stopped="converged"),
        associated_points=100,
        total_glrt_points=200,
        associated_tracks=3,
    )


def record(start_id, start, point, score):
    return dict(
        case="DSX01-S01",
        method="synthetic",
        start_id=start_id,
        start_east_north_km=start,
        arms=dict(c0=arm(point, score), fitted_c=arm(point, score - 7)),
    )


def test_endpoint_group_cannot_merge_a_long_chain_of_nearby_endpoints():
    points = np.array([[0, 0], [0.4, 0], [0.8, 0], [1.2, 0]])
    labels = endpoint_groups(points, threshold_km=0.5)
    assert len(set(labels)) == 2
    for label in set(labels):
        group = points[labels == label]
        assert np.max(np.linalg.norm(group[:, None] - group[None, :], axis=2)) <= 0.5
    order = [3, 0, 2, 1]
    np.testing.assert_array_equal(endpoint_groups(points[order]), labels[order])


def test_losses_are_referenced_within_arm_and_label_membership_changes_count():
    rows = summarize([
        record("start_00", [0, 0], [1, 1], 20),
        record("start_01", [5, 0], [1.1, 1], 30),
    ])
    assert [row["loss_above_best_start_same_arm"] for row in rows] == [0, 0, 10, 10]
    assert all(row["associated_percent"] == 50 for row in rows)
    assert assignment_difference(
        dict(assignment_labels={"A": 1, "B": 2}),
        dict(assignment_labels={"A": 1, "C": 2}),
    ) == 2
    assert assignment_difference({}, {}) is None


def test_no_trajectory_is_invented_when_only_endpoints_are_available():
    assert trajectory(arm([1, 2], 5), [0, 0]) is None
    data = arm([1, 2], 5)
    data["fit"]["history"] = [dict(parameters=[0.5, 0.2, 99])]
    np.testing.assert_allclose(trajectory(data, [0, 0]), [[0, 0], [0.5, 0.2], [1, 2]])


def test_round_paths_keep_common_c0_reanchor_discontinuity_explicit():
    first = dict(parameters=[2, 3], history=[dict(parameters=[1, 1])])
    second = dict(parameters=[6, 7], history=[dict(parameters=[5, 5])])
    data = record("start_00", [0, 0], [6, 7], 5)
    data["rounds"] = [
        dict(start_east_north_km=[0, 0], fits=dict(fitted_c=first)),
        dict(start_east_north_km=[4, 4], fits=dict(fitted_c=second)),
    ]
    paths = round_trajectories(data, "fitted_c")
    assert len(paths) == 2
    np.testing.assert_array_equal(paths[0][2][-1], [2, 3])
    np.testing.assert_array_equal(paths[1][2][0], [4, 4])


def test_raw_denominator_counts_unique_points_not_track_membership(tmp_path):
    path = tmp_path / "raw.jsonl"
    path.write_text("\n".join(json.dumps(row) for row in [
        dict(source_id="S01", observation_id="a"),
        dict(source_id="S01", observation_id="a"),
        dict(source_id="S01", observation_id="untracked"),
        dict(source_id="S02", observation_id="a"),
    ]))
    counts, digest = raw_denominators(path)
    assert counts == {"DSX01-S01": 2, "DSX01-S02": 1}
    assert len(digest) == 64


def test_partial_report_preserves_nonfinite_and_failed_attempts(tmp_path):
    good = record("start_00", [0, 0], [1, 1], 5)
    incomplete = record("start_01", [5, 0], [2, 2], 8)
    incomplete["arms"]["fitted_c"]["fit"]["score"] = float("nan")
    for row in (good, incomplete):
        path = tmp_path / row["case"] / row["method"] / row["start_id"] / "result.json"
        path.parent.mkdir(parents=True)
        path.write_text(json.dumps(row))
    failed = tmp_path / "DSX01-S01/synthetic/start_02/failure.json"
    failed.parent.mkdir()
    failed.write_text(json.dumps(dict(error="synthetic failure")))
    (tmp_path / "protocol.json").write_text(json.dumps(dict(expected_worker_results=3)))
    audit = run(tmp_path)
    assert audit["completed_worker_results"] == 2
    assert audit["finite_arm_endpoints"] == 3
    assert len(audit["failures"]) == 2
    assert audit["expected"]["expected_worker_results"] == 3
    assert (tmp_path / "DSX01-S01/synthetic/restart_basins.png").exists()
    assert (tmp_path / "DSX01-S01/synthetic/restart_loss.png").exists()
    assert "Partial reports do not imply completion" in (tmp_path / "README.md").read_text()
    assert len(json.loads((tmp_path / "result_bindings.json").read_text())) == 2
    assert audit["groups_redrawn"] == 1
    figure = tmp_path / "DSX01-S01/synthetic/restart_basins.png"
    previous_time = figure.stat().st_mtime_ns
    assert run(tmp_path)["groups_redrawn"] == 0
    assert figure.stat().st_mtime_ns == previous_time
    path = tmp_path / "DSX01-S01/synthetic/start_00/result.json"
    good["arms"]["c0"]["fit"]["score"] = 7
    path.write_text(json.dumps(good))
    assert run(tmp_path)["groups_redrawn"] == 1


def test_compact_record_retains_plot_evidence_without_large_nuisance_arrays():
    data = record("start_00", [0, 0], [1, 2, 999], 5)
    data["arms"]["c0"]["state"] = dict(covariance=[1] * 1000)
    data["arms"]["c0"]["fit"]["history"] = [dict(parameters=[0.5, 0.7, 999])]
    data["arms"]["c0"]["rows"] = [dict(component="curve", candidate_norad=123)]
    result = compact_record(data)
    assert "state" not in result["arms"]["c0"]
    assert result["arms"]["c0"]["assignment_labels"] == {"curve": "123"}
    assert result["arms"]["c0"]["fit"]["parameters"] == [1, 2]
    assert result["arms"]["c0"]["fit"]["history"] == [dict(parameters=[0.5, 0.7])]
