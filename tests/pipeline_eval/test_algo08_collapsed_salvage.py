from types import SimpleNamespace

import numpy as np

from leo.analysis.localization_v3 import (
    conservative_recovery, event_position, family_weighting, history_position,
    predictive_linear, retained_position,
)
from tools.pipeline_eval.variants import algo08_collapsed_linear, algo08_collapsed_salvage


def test_full_curved_support_uses_the_same_single_predictive_refit(monkeypatch):
    signed = dict(scan=object(), node={}, keep=np.ones(2, dtype=bool))
    expected = object()
    monkeypatch.setattr(algo08_collapsed_linear, "admit", lambda *_: (expected, {"accepted": True}))
    result, meta = algo08_collapsed_salvage.recover(signed, 12.5)
    assert result is expected and meta["linear"]["accepted"]
    assert meta["masked_points"] == meta["recovered_points"] == 0


def test_recovery_reuses_curved_endpoint_then_tries_one_common_pair(monkeypatch):
    current = dict(endpoint_east_north_km=[-1., 1.], phase_reference=[0.1])
    node = dict(seed=dict(rows=[dict(component="curve", candidate_index=1)]))
    replacement = dict(seed=dict(rows=[dict(component="curve", candidate_index=2)]))
    signed = dict(arms={"c0": current}, scan=object(), node=node, keep=np.array([True, False]),
                  powers=[1.0], means=[0.0], model={"shrinkage": 1.0})
    recovered = np.array([True, True])
    p = SimpleNamespace(labels=[1], reference=[0.1], rows=node["seed"]["rows"],
                        members=[0], slices=[slice(None)])
    signed["scan"] = SimpleNamespace(tracks=[])

    def nominate(scan, original, keep):
        reused = conservative_recovery.repaired_fit(scan, original, "c0", "unit", keep)
        assert reused[0] is p and reused[1]["parameters"] == [-1., 1.]
        return replacement, recovered, [dict(selected={})]

    calls = []

    def refit(scan, node, keep, arm, powers, means, model, events, entries):
        assert node is replacement and keep is recovered and means[0] == 0.35
        assert events == [] and len(entries) == 1
        calls.append(arm)
        return dict(endpoint_east_north_km=[-1., 1.], final_phase_change_s=0.001,
                    gates=dict(tracks=[dict(component="curve", compatible=True)]),
                    linear_gates=[dict(component="linear", compatible=True)])

    monkeypatch.setattr(conservative_recovery, "salvage", nominate)
    monkeypatch.setattr(conservative_recovery, "retained_metrics", lambda *_: {})
    monkeypatch.setattr(event_position, "make_event_problem", lambda *_: p)
    monkeypatch.setattr(event_position, "refit", refit)
    monkeypatch.setattr(family_weighting, "confidence_for", lambda *_: [1.0])
    monkeypatch.setattr(family_weighting, "family_weights", lambda *_: ([1.0], {}, {}))
    monkeypatch.setattr(retained_position, "phase_widths", lambda *_: ([1.], [{}]))
    monkeypatch.setattr(history_position, "forecast_phase_mean", lambda *_: np.array([0.35]))
    monkeypatch.setattr(predictive_linear, "select_entries", lambda *_: [dict(points=19)])
    result, meta = algo08_collapsed_salvage.recover(signed, 12.5)
    assert calls == ["c0", "fitted_c"] and result["node"] is replacement
    assert meta["selected_trims"] == 1 and meta["accepted"] and meta["linear"]["accepted"]
    assert list(signed["keep"]) == [True, False] and signed["node"] is node
