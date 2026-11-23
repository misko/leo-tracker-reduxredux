from importlib import import_module
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest


@pytest.fixture
def lighter(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / "reports/ALGO08/v3"))
    return import_module("lighter_joint_estimator")


def test_only_observable_confidence_values_need_projection(lighter, monkeypatch):
    from leo.analysis.localization_v3 import family_weighting as stock

    owners = [0, 0, 1, 1, 2, 2]
    rx_lanes = [(1, 1), (1, 2), (1, 3), (2, 5), (2, 1), (2, 2)]
    tracks = [dict(key=str(i), receiver=rx, channel=ch, rf_hz=11.5e9,
                   times=np.arange(6, dtype=float) + i * 10, values=np.arange(6, dtype=float) ** 2)
              for i, (rx, ch) in enumerate(rx_lanes)]
    rows = [dict(active_curvature=True, component=t["key"], candidate_index=j)
            for t, j in zip(tracks, owners, strict=True)]
    node = dict(seed=dict(rows=rows))
    times = np.concatenate([t["times"] for t in tracks])
    kept = np.ones(len(times), bool)
    kept[[1, 4]] = False
    kept[-6:] = False
    scan = SimpleNamespace(tracks=tracks, times=times, sky={}, geometry=times, radio_sigma_hz=150., norads=[11, 22, 33],
                           search_region=SimpleNamespace(half_width_km=12.5, latlon=lambda x: x),
                           rx_basis=[np.zeros((6, 1)) for _ in tracks], hardware=lambda t, _beta: np.zeros(len(t["times"])),
                           index=[np.arange(i * 6, (i + 1) * 6) for i in range(len(tracks))])
    model = SimpleNamespace(rows=rows, members=list(range(len(tracks))),
                            slices=[slice(i * 6, (i + 1) * 6) for i in range(len(tracks))],
                            state=lambda _: dict(beta=np.zeros(8), smooth=[np.zeros(1), np.zeros(1)]))
    for module in (lighter, stock):
        monkeypatch.setattr(module, "problem", lambda *_args: model)
        monkeypatch.setattr(module, "phase_widths", lambda *_args: (np.ones(3), []))
    monkeypatch.setattr(lighter.scan_kernel, "prepare_phase_geometry", lambda _bank, clock: clock)

    def projection(clock, x, y):
        grid = np.arange(3.)[:, None] * 1_100 + clock + x + y
        return grid, np.ones_like(grid), clock[None, :] + np.zeros_like(grid)

    monkeypatch.setattr(stock, "phase_linear_frequency", projection)
    baseline = dict(arms=dict(c0=dict(record=dict(endpoint_east_north_km=[0., 0.], phase_reference=[0., 0., 0.]))))
    expected = stock.confidence_for(scan, node, kept, baseline)
    receipts = []
    actual = lighter.minimum_confidence(scan, node, kept, baseline, receipts=receipts)
    counts = [int(kept[section].sum()) for section in model.slices]
    weights = lambda confidence: stock.family_weights(rows, model.members, tracks, confidence, "cross_rx_support", counts)[0]
    np.testing.assert_array_equal(actual[:2], expected[:2])
    np.testing.assert_array_equal(weights(actual), weights(expected))
    assert receipts[0]["scored_tracks"] == 2 and receipts[0]["compared_times"] == 10


def test_failed_warm_arm_retries_the_exact_cold_pair(lighter, monkeypatch):
    candidate = {"scan": SimpleNamespace(search_region=SimpleNamespace(half_width_km=12.5))}
    cold_calls = []
    warm_calls = []

    def warm(_candidate, _means, arm):
        warm_calls.append(arm)
        return ({"fit": 1}, None) if arm == "c0" else (None, "warm_fit_not_stationary_in_two_refreshes")

    monkeypatch.setattr(lighter, "warm_arm", warm)
    monkeypatch.setattr(lighter, "readout", lambda value: value)
    monkeypatch.setattr(lighter.blind_joint_signed, "fitted_pair",
                        lambda *args: cold_calls.append(args) or dict(c0="cold", fitted_c="cold"))
    measured = {}
    out = lighter.fit_pair(candidate, [0.], measured)
    assert out == dict(c0="cold", fitted_c="cold") and warm_calls == list(lighter.ARMS)
    assert len(cold_calls) == 1 and not measured["warm_signed_fit"]["accepted"]
    assert "cold_fallback_clocks" in measured["warm_signed_fit"]


def test_warm_fit_starts_from_its_own_arm_and_requires_small_original_step(lighter, monkeypatch):
    scan = SimpleNamespace(search_region=SimpleNamespace(half_width_km=12.5))
    candidate = dict(scan=scan, node={"seed": {"rows": [{"candidate_index": 0}]}}, keep=[True], powers=[1.], entries=[],
                     model={}, arms={"c0": dict(endpoint_east_north_km=[1., 2.], state={"phases": np.array([.4])}),
                                     "fitted_c": dict(endpoint_east_north_km=[-1., 2.], state={"phases": np.array([.5])})})
    values = []
    current = SimpleNamespace(labels=[0], state=lambda _point: {"phases": np.array([.501])})

    def build(_scan, _node, _keep, arm, reference, *_args):
        values.append((arm, float(reference[0])))
        return current

    monkeypatch.setattr(lighter.event_position, "make_event_problem", build)
    monkeypatch.setattr(lighter.event_position, "attach_event_predictive", lambda *_args: None)
    monkeypatch.setattr(lighter.event_position, "cached", lambda _: None)
    monkeypatch.setattr(lighter.event_position, "summary", lambda _model, point, _entries: {"position": list(point)})
    monkeypatch.setattr(lighter.position, "fit", lambda model, point, **_: dict(parameters=point, score=1., stopped="small_bounded_step"))
    accepted, reason = lighter.warm_arm(candidate, [.5], "fitted_c")
    assert accepted["position"] == [-1., 2.] and reason is None and values == [("fitted_c", .5)]
    monkeypatch.setattr(lighter.position, "fit", lambda model, point, **_: dict(parameters=point, score=1., stopped="iteration_budget"))
    declined, reason = lighter.warm_arm(candidate, [.5], "fitted_c")
    assert declined is None and reason == "warm_fit_not_stationary_in_two_refreshes"
