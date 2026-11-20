from types import SimpleNamespace

import numpy as np

from tools.pipeline_eval.variants import portable_gate as gate
from tools.pipeline_eval.variants import portable_gate_coverage as coverage
from tools.pipeline_eval.variants import portable_gate_halo as halo


def test_clock_partition_uses_only_native_time_and_withholds_full_blocks():
    rows = [{"time_s": t} for t in (0, 8.9, 9, 11.99, 12, 20.9, 21, 23.99, 24)]
    train, held = gate.partition(rows)
    assert train == [rows[i] for i in (0, 1, 4, 5, 8)]
    assert held == [rows[i] for i in (2, 3, 6, 7)]


def test_profile_recovers_an_independent_train_only_alias_and_phase():
    slope = np.vstack([np.linspace(-300, 600, 20), np.repeat(10, 20)])
    offset, injected_phase = 10300.0, 0.45
    want = offset + slope[0] * injected_phase
    cost, level, phase = gate.phase_profile(want - np.zeros_like(slope), slope, 1.0, 30)
    assert cost[0] < cost[1]
    assert abs(level[0] - offset) < 1
    assert abs(phase[0] - injected_phase) < 0.001
    assert phase[1] == 0
    period = gate.portable_v5.TRACK_CONFIG["alias_spacing_hz"]
    assert np.allclose(gate.wrap(np.array([10, 10 + period, 10 - period])), 10)


def test_gate_needs_distinct_sources_frequency_and_time():
    support = dict(good_families=4, good_channels=2, good_time_bins=3)
    assert gate.admit(support)
    for key in support:
        assert not gate.admit(dict(support, **{key: support[key] - 1}))


def test_bounded_recovery_keeps_the_stable_pair_without_refitting_unchanged_rows():
    calls = []
    initial = np.array([True, True, False])
    kept = np.array([True, False, False])
    node, fit = object(), object()

    def original(scan, node, mask, stage):
        calls.append(stage)
        return "problem", kept, fit, ["checkpoint"], True

    def stock_salvage(*args, **kwargs):
        raise AssertionError("the exhaustive stock salvage search is outside the bounded policy")

    module = SimpleNamespace(fit_and_gate=original, salvage=stock_salvage)

    def recover():
        _, retained, arms, _, stable = module.fit_and_gate(None, node, initial, "exclude_refit")
        new_node, same, trims = module.salvage(None, node, retained)
        _, repeated, retried_arms, history, still_stable = module.fit_and_gate(
            None, new_node, same, "salvage_refit"
        )
        return repeated is kept and arms is retried_arms and stable and still_stable, trims, history

    result, diagnostics = gate.retain_only(module, recover)
    assert result == (True, [], [])
    assert calls == ["exclude_refit"]
    assert diagnostics == {"points_excluded_before_salvage": 2}
    assert module.fit_and_gate is original
    assert module.salvage is stock_salvage


def test_halo_compares_predictions_on_the_same_held_data_and_counts_an_orbit_once(monkeypatch):
    arc = SimpleNamespace(held_time=np.arange(6), held_y=np.repeat(1000.0, 6), scale=1)
    sky = dict(
        time_s=np.arange(6), position_km=np.zeros((1, 6, 3)), velocity_km_s=np.zeros((1, 6, 3))
    )
    monkeypatch.setattr(halo.orbit_projector, "prepare", lambda *args: None)
    region = SimpleNamespace(latlon=lambda point: point)

    def predict(grid, east, north):
        model = np.full((1, 6), east * 1000)
        return model, np.ones((1, 6)), None

    projector = SimpleNamespace(evaluate=predict)
    selected = [(arc, 0, 0, 0), (arc, 0, 0, 0)]
    near = halo.validation_score((1, (1, 0), selected), sky, region, projector, 150)
    far = halo.validation_score((1, (2, 0), selected), sky, region, projector, 150)
    duplicate_eliminated = halo.validation_score(
        (1, (1, 0), selected[:1]), sky, region, projector, 150
    )
    assert near > np.log(20)
    assert far == 0
    assert near == duplicate_eliminated


def test_coverage_denominator_counts_distinct_time_and_rf_but_collapses_receiver_duplicates():
    a = SimpleNamespace(channel=1, scale=1.0, train_time=np.array([0, 40]))
    b = SimpleNamespace(channel=1, scale=1.0, train_time=np.array([3, 42]))
    c = SimpleNamespace(channel=1, scale=1.0, train_time=np.array([31, 70]))
    d = SimpleNamespace(channel=3, scale=1.0, train_time=np.array([3, 42]))
    e = SimpleNamespace(channel=1, scale=0.9, train_time=np.array([0, 40]))
    grouped = list(coverage.units([b, a, c, d, e]))
    assert [[id(x) for x in record] for record in grouped] == [
        [id(a), id(b)],
        [id(c)],
        [id(d)],
        [id(e)],
    ]
