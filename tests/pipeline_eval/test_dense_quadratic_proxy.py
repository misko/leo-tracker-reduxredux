from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest


@pytest.fixture
def research(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / "reports/ALGO08/v3"))


@pytest.mark.parametrize("degree", (0, 1, 2))
def test_endpoint_gate_matches_original_at_the_binary64_bound(research, degree):
    from leo.analysis import polynomial_tracklets as poly
    from quadratic_endpoint_slope import endpoint_test

    rng = np.random.default_rng(23)
    for _ in range(25):
        t = rng.uniform(-100., 200., 10)
        indices = np.array([1, 7, 3, 5])
        coeff = rng.normal(0., 1e4, degree + 1)
        reference, scale = rng.uniform(-10., 25., 2)
        scale = max(abs(scale), 1.)
        piece = dict(indices=indices, coefficients_hz=coeff, reference_time_s=reference, time_scale_s=scale)
        support = t[indices]
        endpoints = (np.array([support.min(), support.max()]) - reference) / scale
        slope = np.max(np.abs(poly.leg.legval(endpoints, poly.leg.legder(coeff)) / scale))
        for maximum in (np.nextafter(slope, -np.inf), slope, np.nextafter(slope, np.inf)):
            cfg = SimpleNamespace(max_slope_hz_s=maximum)
            assert endpoint_test(piece, t, cfg) is poly._bounded_slope(piece, t, cfg)


def test_scoped_slope_gate_delegates_higher_degree_and_non_binary64(research):
    from leo.analysis import polynomial_tracklets as poly
    from quadratic_endpoint_slope import endpoint_slope

    original = poly._bounded_slope
    times = np.array([-1., 0., 1.])
    settings = SimpleNamespace(max_slope_hz_s=2.)
    pieces = [dict(indices=np.arange(3), coefficients_hz=coeff, reference_time_s=0., time_scale_s=1.)
              for coeff in (np.array([0., 3.]), np.array([0., -3., 0., 1.]), np.array([0., 2.], dtype=np.float32))]
    expected = [original(piece, times, settings) for piece in pieces]
    with endpoint_slope() as counts:
        assert [poly._bounded_slope(piece, times, settings) for piece in pieces] == expected
        assert counts == dict(endpoint_checks=1, original_checks=2)
    assert poly._bounded_slope is original


def test_owner_deltas_keep_role_changes_separate_from_norad_switches(research):
    from dense_quadratic_proxy_score import owner_deltas

    a = [["first", 8, "curved"], ["second", 8, "linear"], ["lost", 17, "curved"]]
    b = [["first", 8, "linear"], ["second", 9, "linear"], ["new", 21, "curved"]]
    assert owner_deltas(a, b) == dict(common=2, lost=1, new=1, same_satellite_and_role=0,
                                     changed_satellite=1, changed_role=1, family_counts=[2, 3])
    with pytest.raises(ValueError, match="Duplicate observation owner"):
        owner_deltas(a + a[:1], b)


def test_graph_gate_requires_exact_preparation_and_savings_in_each_order(research, monkeypatch, tmp_path):
    import dense_quadratic_proxy_score as score

    data = {}
    for i, (mode, cpu) in enumerate(zip(score.GRAPH_MODES, (2.4, 2.0, 2.0, 2.3), strict=True), 1):
        path = tmp_path / f"graph-{i}-{mode}.json"
        path.touch()
        data[path] = dict(graph_trial_mode=mode, kernel=dict(endpoint_checks=10) if mode == "endpoint" else {},
                          graph=dict(graph_sha256="same", clocks=dict(prepare_tracks=[dict(cpu_s=cpu)])))
    monkeypatch.setattr(score, "read", data.__getitem__)
    gate, _ = score.graph_gate(tmp_path, "same")
    assert gate["full_replay_allowed"] and gate["mean_saved_cpu_s"] == pytest.approx(.35)
    changed = data[tmp_path / "graph-3-endpoint.json"]["graph"]
    changed["clocks"]["prepare_tracks"][0]["cpu_s"] = 2.35
    assert not score.graph_gate(tmp_path, "same")[0]["full_replay_allowed"]
    changed["graph_sha256"] = "changed"
    with pytest.raises(ValueError, match="prepared Graph"):
        score.graph_gate(tmp_path, "same")
