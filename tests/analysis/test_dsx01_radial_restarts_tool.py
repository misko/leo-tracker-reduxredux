"""Fresh-start coordinates and paired control isolation without RF fixtures."""

import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))
import dsx01_radial_restarts as restart  # noqa: E402


@pytest.mark.parametrize("point", [[np.nan, 0], [13, 0], [0], [0, 0, 0]])
def test_restart_rejects_invalid_regional_coordinates(point):
    with pytest.raises(ValueError, match="25-km box"):
        restart.validated_start(point)


def test_assignment_change_count_follows_components_when_rows_reordered():
    def node(rows, aliases):
        return dict(
            seed=dict(rows=[dict(component=c, candidate_index=j) for c, j in rows]),
            aliases=aliases,
        )

    old = node([("a", 1), ("b", 2)], [0, 1])
    new = node([("b", 2), ("a", 3)], [2, 0])
    assert restart.assignment_changes(old, new) == dict(
        changed_components=2, changed_satellite_labels=1, changed_aliases=1
    )


def test_independent_discovery_uses_requested_start_and_zero_baseline(monkeypatch):
    point = np.array([5.0, -5.0])
    rows = [dict(component="curve", candidate_index=0)]
    scan = SimpleNamespace(case="synthetic", norads=[101, 102], sigma=np.ones(2))
    statistics = dict(
        ci=np.array([0]), mean=np.zeros((1, 2)), hm=np.zeros((1, 2)),
        xz=np.zeros((1, 2)), xh=np.zeros((1, 2)), rss=np.ones((1, 2)),
        zh=np.zeros((1, 2)), hh=np.ones((1, 2)), xx=np.ones(1),
        starts=np.array([0]), count=np.ones(1),
    )
    anchors, incoming = [], []

    def discover_stats(_scan, anchor):
        anchors.append(np.array(anchor))
        return (None, None, None), statistics

    def phases(_stats, beta, _sigma, _bounds, return_components=False):
        result = np.zeros(2) if not return_components else np.zeros((1, 2))
        return (result, None) if return_components else result

    def association(state, _base, native, _method):
        incoming.append(np.array(state["beta"]))
        np.testing.assert_array_equal(native, point)
        return None, rows, None, None

    def zero(_scan):
        return dict(beta=np.zeros(8), phases=np.zeros(2), extra={}, smooth=np.zeros((2, 1)))

    def aliases(_scan, _seed, anchor):
        anchors.append(np.array(anchor))
        return [2]

    class Problem:
        def __init__(self, seed, alias):
            self.rows, self.seed, self.alias = seed["rows"], seed, alias

        def residual(self, anchor):
            anchors.append(np.array(anchor))
            return np.array([1.0])

        def state(self, anchor):
            anchors.append(np.array(anchor))
            return self.seed["state"]

    def explore(_scan, state, anchor, _method, compact_update):
        assert not compact_update
        anchors.append(np.array(anchor))
        return dict(rows=rows, state=state), dict(candidate_hypotheses=2, explored_candidates=2)

    scan.association = association
    monkeypatch.setattr(restart, "discovery_statistics", discover_stats)
    monkeypatch.setattr(restart, "zero_state", zero)
    monkeypatch.setattr(restart, "proposal_phases", phases)
    monkeypatch.setattr(restart.matching, "seed_calibrations", lambda *_: [np.zeros(8), np.ones(8)])
    monkeypatch.setattr(restart, "improve", lambda _s, beta, phase, *_a, **_k: (None, beta, phase))
    monkeypatch.setattr(restart, "project_radio_state", lambda state: state)
    monkeypatch.setattr(restart, "native_point", lambda _scan, anchor: anchor)
    monkeypatch.setattr(restart, "nomination_rows", lambda *_: rows)
    monkeypatch.setattr(restart, "aliases_at_start", aliases)
    monkeypatch.setattr(
        restart, "standard_problem", lambda _scan, seed, _sigma, aliases: Problem(seed, aliases)
    )
    monkeypatch.setattr(restart, "explore", explore)
    result = restart.discover_at_start(scan, 150, point, budget=2)
    np.testing.assert_array_equal(incoming[0], np.zeros(8))
    np.testing.assert_array_equal(incoming[1], np.ones(8))
    for anchor in anchors:
        np.testing.assert_array_equal(anchor, point)
    assert result["aliases"] == [2]
    assert result["discovery_provenance"]["proposal_hypotheses_run"] == 2
    assert result["discovery_provenance"]["saved_atlas_labels_calibration_or_site_read"] is False


@pytest.mark.parametrize(
    "proposal_score, expected", [(1.0, "all_candidate_refresh"), (9.0, "incumbent")]
)
def test_reassociation_keeps_incumbent_unless_recipe_c0_score_improves(
    monkeypatch, proposal_score, expected
):
    state = dict(beta=np.zeros(8), phases=np.zeros(2), extra={}, smooth=np.zeros((2, 1)))
    node = dict(
        seed=dict(rows=[dict(component="curve", candidate_index=0)], state=state), aliases=[0]
    )
    proposal = dict(rows=[dict(component="curve", candidate_index=1)], state=state)
    monkeypatch.setattr(
        restart, "explore", lambda *_a, **_k: (
            proposal, dict(candidate_hypotheses=2, explored_candidates=2)
        )
    )
    monkeypatch.setattr(restart, "aliases_at_start", lambda *_: [2])

    def factory(_scan, candidate, _sigma, name, fitted_c):
        assert name == "clock_variance" and fitted_c is False
        value = proposal_score if candidate["seed"]["rows"][0]["candidate_index"] else 4.0
        return SimpleNamespace(residual=lambda _x: np.array([np.sqrt(value)]))

    monkeypatch.setattr(restart, "factory", factory)
    selected, detail = restart.refresh_modern_assignment(
        None, 150, "clock_variance", node, state, np.array([5.0, 0.0])
    )
    assert detail["selected"] == expected
    assert selected["aliases"] == ([2] if expected == "all_candidate_refresh" else [0])


def test_modern_rounds_share_c0_anchor_and_refreshed_labels_between_arms(monkeypatch):
    original = dict(
        rows=[dict(component="curve", candidate_index=0, candidate_norad=101)], state={}
    )
    discovery = dict(
        start_east_north_km=[-5.0, 0.0], seed=original, aliases=[0],
        hypothesis=0, discovery_provenance={"zero_initial_radio_phase_and_smooth": True},
    )
    calls, refreshes = [], []

    class Problem:
        def __init__(self, node, fitted):
            self.rows = node["seed"]["rows"]
            self.alias = list(node["aliases"])
            self.labels = [self.rows[0]["candidate_index"]]
            self.members, self.flat_times = [0], np.arange(6.0)
            self.reference = np.zeros(1)
            self.initial, self.lower, self.upper = np.zeros(2), np.full(2, -12.5), np.full(2, 12.5)
            self.target = np.array([3.0, 4.0]) if fitted else np.array([1.0, 2.0])

        def residual(self, xy):
            return np.asarray(xy) - self.target

        def state(self, xy):
            return dict(beta=np.zeros(8), phases=np.zeros(2), extra={}, smooth=np.zeros((2, 1)))

        def calculate(self, xy):
            return dict(conditional_residual_hz=np.zeros(6))

    def factory(_scan, node, _sigma, _name, fitted):
        calls.append((fitted, node["seed"]["rows"][0]["candidate_index"], list(node["aliases"])))
        return Problem(node, fitted)

    def refresh(_scan, _sigma, _name, _node, _state, anchor):
        refreshes.append(np.array(anchor))
        return dict(
            seed=dict(
                rows=[dict(component="curve", candidate_index=1, candidate_norad=102)], state={}
            ),
            aliases=[3],
        ), {}

    monkeypatch.setattr(restart, "factory", factory)
    monkeypatch.setattr(restart, "refresh_modern_assignment", refresh)
    monkeypatch.setattr(
        restart, "actual_metrics", lambda *_: dict(accepted_points=6, accepted_tracks=1)
    )
    result = restart.run_modern_recipe(SimpleNamespace(case="synthetic"), 150, discovery, "normal")
    assert calls == [(False, 0, [0]), (True, 0, [0]), (False, 1, [3]), (True, 1, [3])]
    np.testing.assert_allclose(refreshes[0], [1, 2], atol=1e-5)
    np.testing.assert_allclose(result["rounds"][1]["start_east_north_km"], [1, 2], atol=1e-5)
    for record in result["rounds"]:
        for fit in record["fits"].values():
            np.testing.assert_allclose(
                fit["history"][0]["parameters"], record["start_east_north_km"]
            )
    assert result["arms"]["c0"]["associated_points"] == 6
    assert original["rows"][0]["candidate_index"] == 0
    assert result["final_node"]["aliases"] == [3]


def test_native_band_proposals_project_actual_hz_mean_to_standard_rf_scaled_basis():
    basis = np.zeros((2, 11))
    basis[:, 0] = 1
    state = dict(
        beta=np.zeros(8), phases=np.zeros(2), extra={}, smooth=np.arange(44.0).reshape(2, 22)
    )
    scan = SimpleNamespace(
        rx_basis=[basis.copy(), basis.copy()],
        tracks=[dict(receiver=1), dict(receiver=2)],
    )
    p = SimpleNamespace(
        scan=scan, flat_times=np.arange(4.0), members=[0, 1],
        slices=[slice(0, 2), slice(2, 4)], q=np.array([1.0, 2.0, 1.0, 2.0]),
        state=lambda _x: state,
        nonlinear_radio_mean=lambda _x: np.array([10.0, 10.0, 20.0, 20.0]),
    )
    proposal = restart.proposal_state(p, [0, 0])
    assert proposal["smooth"].shape == (2, 11)
    np.testing.assert_allclose(proposal["smooth"][:, 0], [6.0, 12.0])
    np.testing.assert_allclose(proposal["smooth"][:, 1:], 0)
    assert state["smooth"].shape == (2, 22)
    np.testing.assert_array_equal(state["smooth"], np.arange(44.0).reshape(2, 22))


def test_native_gate_prediction_adds_native_mean_once_and_zeros_only_adapter_smooth():
    state = dict(
        beta=np.zeros(8), phases=np.zeros(2), extra={}, smooth=np.ones((2, 22))
    )
    p = SimpleNamespace(
        scan=SimpleNamespace(rx_basis=[np.zeros((2, 11))]), supported=[0],
        q=np.array([1.0, 2.0]), state=lambda _x: dict(state),
        conditional_frequency=lambda _x: (np.array([100.0, 100.0]), np.ones(2)),
        nonlinear_radio_mean=lambda _x: np.array([10.0, 10.0]),
        calculate=lambda _x: {"conditional_residual_hz": np.zeros(2)},
    )
    proxy = restart.metric_problem(p)
    frequency, _ = proxy.conditional_frequency([0, 0])
    np.testing.assert_allclose(p.q * frequency, [110.0, 210.0])
    assert proxy.state([0, 0])["smooth"].shape == (2, 11)
    assert not proxy.state([0, 0])["smooth"].any()
    assert p.state([0, 0])["smooth"].shape == (2, 22)
    np.testing.assert_array_equal(
        proxy.calculate([0, 0])["conditional_residual_hz"],
        p.calculate([0, 0])["conditional_residual_hz"],
    )
