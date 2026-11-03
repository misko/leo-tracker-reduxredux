"""Independent-start legacy/linear adapter and campaign isolation contracts."""

import json
import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))
import dsx01_radial_legacy_linear as adapters  # noqa: E402
import run_dsx01_radial_restarts as campaign  # noqa: E402


class LegacyWrapper:
    def __init__(self, alias):
        self.problem = SimpleNamespace(alias=list(alias))

    def __getattr__(self, name):
        return getattr(self.problem, name)


def test_paired_aliases_write_underlying_legacy_problem_for_both_arms():
    problems = {"c0": LegacyWrapper([2, 3]), "fitted_c": LegacyWrapper([8, 9])}
    adapters.paired_aliases(problems, [4, -2])
    for problem in problems.values():
        assert problem.problem.alias == [4, -2]
        assert problem.alias == [4, -2]
        assert "alias" not in vars(problem)
    problems["c0"].problem.alias.append(7)
    assert problems["fitted_c"].problem.alias == [4, -2]


def test_linear_nomination_uses_only_this_starts_c0_curved_parent(monkeypatch):
    parent_point = np.array([1.0, 2.0])
    reference = {"same_start": True}
    parent = dict(
        final_node={"identity": "fresh"}, final_reference=reference, rounds=[{"round": 0}],
        arms={
            "c0": dict(fit=dict(parameters=parent_point)),
            "fitted_c": dict(fit=dict(parameters=np.array([11.0, 12.0]))),
        },
    )
    created, nomination_calls, fitted_starts, selections = [], [], [], []

    def factory(scan, node, sigma, method, fitted_c, reference):
        assert node is parent["final_node"] and reference is parent["final_reference"]
        assert method == "normal"
        p = SimpleNamespace(fitted_c=fitted_c, rows=[], alias=[3], state=lambda x: {})
        created.append(p)
        return p

    def metrics(p, fit, arm, point):
        return dict(
            tracks=[dict(component="curve", compatible=True, points=10, norad=123)],
            accepted_native_rms_hz=30.0,
        )

    def nominations(p, point, metrics):
        nomination_calls.append((p, np.asarray(point).copy()))
        return [
            dict(component="strict", accepted=True, points=5),
            dict(component="fails_white", accepted=True, points=9),
            dict(component="rejected", accepted=False, points=6),
        ]

    def linear_metrics(p, point, selected):
        return [dict(
            component=row["component"], compatible=row["component"] == "strict",
            norad=123, points=row["points"],
        ) for row in selected]

    class CutScore:
        def __init__(self, p, selected, kind):
            assert kind == "joint"
            self.selected = [row for row in selected if row["accepted"]]
            selections.append((p, self.selected))

        def score(self, point):
            return dict(total=float(np.sum(np.asarray(point) ** 2)))

    def fit(function, point, iterations):
        fitted_starts.append(np.asarray(point).copy())
        assert iterations == 7
        return dict(parameters=np.asarray(point) + [0.1, 0.2], score=function(point))

    monkeypatch.setattr(adapters, "factory", factory)
    monkeypatch.setattr(adapters, "actual_metrics", metrics)
    monkeypatch.setattr(adapters, "nominations_for", nominations)
    monkeypatch.setattr(adapters, "linear_metrics", linear_metrics)
    monkeypatch.setattr(adapters, "CutScore", CutScore)
    monkeypatch.setattr(adapters, "bounded_scalar_newton", fit)
    result = adapters.run_linear_recipe(object(), 50, parent, "white_joint", iterations=7)
    assert len(nomination_calls) == 1
    assert nomination_calls[0][0] is created[0] and not created[0].fitted_c
    np.testing.assert_array_equal(nomination_calls[0][1], parent_point)
    np.testing.assert_array_equal(fitted_starts, [parent_point, parent_point])
    assert [[row["component"] for row in selected] for _, selected in selections] == [
        ["strict"], ["strict"]
    ]
    assert result["calibration_from_curves_only"] is True
    assert all(arm["associated_points"] == 15 for arm in result["arms"].values())


def test_gate_summary_keeps_acceptance_distinct_from_all_proposed_points():
    result = adapters.gate_summary(dict(
        tracks=[
            dict(component="accepted", compatible=True, points=20, norad=5),
            dict(component="rejected", compatible=False, points=100, norad=6),
        ],
        all_curved_native_rms_hz=77.0,
    ))
    assert result["associated_points"] == 20 and result["associated_tracks"] == 1
    assert len(result["track_associations"]) == 2


def test_layout_and_dependencies_never_cross_start_or_scan():
    starts = np.array(campaign.STARTS)
    assert starts.shape == (13, 2)
    assert len(np.unique(starts, axis=0)) == 13
    assert np.all(np.linalg.norm(starts, axis=1) <= 10)
    assert np.all(abs(starts) <= 12.5)
    np.testing.assert_array_equal(starts[0], [0, 0])
    assert campaign.dependencies("DSX01-S02", "discover", 7) == []
    assert campaign.dependencies("DSX01-S02", "normal", 7) == [("DSX01-S02", "discover", 7)]
    assert campaign.dependencies("DSX01-S02", "linear_joint", 7) == [
        ("DSX01-S02", "discover", 7), ("DSX01-S02", "normal", 7),
    ]


def test_resume_rejects_existing_artifacts_from_other_source_versions(tmp_path):
    path = tmp_path / "result.json"
    assert not campaign.valid_result(path, "current")
    path.write_text(json.dumps(dict(source_fingerprint="old", status="complete")))
    with pytest.raises(ValueError, match="another source version"):
        campaign.valid_result(path, "current")
    path.write_text(json.dumps(dict(source_fingerprint="current", status="partial")))
    assert not campaign.valid_result(path, "current")
    path.write_text(json.dumps(dict(source_fingerprint="current", status="complete")))
    assert campaign.valid_result(path, "current")


def test_source_fingerprint_changes_when_any_campaign_source_changes(tmp_path, monkeypatch):
    path = tmp_path / "worker.py"
    path.write_text("version one")
    monkeypatch.setattr(campaign, "ROOT", tmp_path)
    monkeypatch.setattr(campaign, "SOURCES", [path])
    before = campaign.fingerprint()
    path.write_text("version two")
    assert campaign.fingerprint() != before


def test_read_guard_rejects_external_gps_and_saved_endpoint_artifacts():
    guard = campaign.RestartReadGuard(campaign.CLEAN)
    for name in ("gps_invariance.json", "endpoints.json", "position_and_gradient_summary.json"):
        with pytest.raises(ValueError, match="forbidden"):
            guard.check_path(str(campaign.ROOT / "reports/external" / name))
    guard.check_path(str(campaign.OUTPUT / "DSX01-S01/discovery/start_00/discovery.json"))
    assert len(guard.read_paths) == 1


def test_worker_rejects_another_starts_discovery_before_inference(tmp_path, monkeypatch):
    output, clean = tmp_path / "output", tmp_path / "clean"
    case, start_id = "DSX01-S01", 1
    monkeypatch.setattr(campaign, "OUTPUT", output)
    monkeypatch.setattr(campaign, "CLEAN", clean)
    monkeypatch.setattr(campaign, "fingerprint", lambda: "binding")
    monkeypatch.setattr(campaign.RestartReadGuard, "install", lambda self: None)
    monkeypatch.setattr(campaign, "load_scan", lambda case: (SimpleNamespace(), 10))
    history = clean / case / "causal_history.json"
    history.parent.mkdir(parents=True)
    history.write_text("{}")
    path = campaign.result_path(case, "discover", start_id)
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps(dict(
        case=case, start_id=start_id, source_fingerprint="binding", status="complete",
        start_east_north_km=[0, 0],
    )))
    with pytest.raises(ValueError, match="starting position|same-start"):
        campaign.worker(case, "normal", start_id)


@pytest.mark.parametrize("mismatch", ["case", "start_id", "start_east_north_km"])
def test_worker_rejects_misplaced_linear_parent_even_with_current_fingerprint(
    tmp_path, monkeypatch, mismatch
):
    output, clean = tmp_path / "output", tmp_path / "clean"
    case, start_id = "DSX01-S01", 1
    monkeypatch.setattr(campaign, "OUTPUT", output)
    monkeypatch.setattr(campaign, "CLEAN", clean)
    monkeypatch.setattr(campaign, "fingerprint", lambda: "binding")
    monkeypatch.setattr(campaign.RestartReadGuard, "install", lambda self: None)
    monkeypatch.setattr(campaign, "load_scan", lambda case: (SimpleNamespace(), 10))
    history = clean / case / "causal_history.json"
    history.parent.mkdir(parents=True)
    history.write_text("{}")
    receipt = dict(
        case=case, start_id=start_id, source_fingerprint="binding", status="complete",
        start_east_north_km=list(campaign.STARTS[start_id]),
    )
    discovery = campaign.result_path(case, "discover", start_id)
    discovery.parent.mkdir(parents=True)
    discovery.write_text(json.dumps(receipt))
    parent = campaign.result_path(case, "normal", start_id)
    parent.parent.mkdir(parents=True)
    bad = dict(receipt)
    bad[mismatch] = {
        "case": "DSX01-S02", "start_id": 0, "start_east_north_km": [0, 0]
    }[mismatch]
    parent.write_text(json.dumps(bad))
    with pytest.raises(ValueError, match="normal parent belongs"):
        campaign.worker(case, "linear_joint", start_id)
