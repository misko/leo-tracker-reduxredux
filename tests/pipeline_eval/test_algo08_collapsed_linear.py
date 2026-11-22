from types import SimpleNamespace

import pytest

from leo.analysis.localization_v3 import event_position, predictive_linear
from tools.pipeline_eval.variants import algo08_collapsed_linear


def selected_arm(arm, valid):
    return dict(endpoint_latlon=[1.2, 2.5], endpoint_east_north_km=[-0.1, 0.3],
                phase_reference=[0.0], final_phase_change_s=0.0, arm=arm,
                gates=dict(tracks=[dict(component="curve", compatible=True)]),
                linear_gates=[dict(component="linear", compatible=valid)])


@pytest.mark.parametrize("qualifies", [True, False])
def test_only_a_qualified_pair_can_adopt_the_linear_add_back(monkeypatch, qualifies):
    scan = SimpleNamespace()
    original = {arm: selected_arm(arm, True) for arm in ("c0", "fitted_c")}
    payload = dict(arms=original, scan=scan, node={}, keep=[True],
                   entries=[], powers=[1.0], means=[0.0], model={})
    calls = []

    def refit(owner, node, keep, arm, powers, means, model, events, entries):
        assert owner is scan and keep is payload["keep"] and powers is payload["powers"]
        assert means is payload["means"] and model is payload["model"] and events == []
        assert len(entries) == 1
        calls.append(arm)
        return selected_arm(arm, qualifies or arm == "c0")

    monkeypatch.setattr(event_position, "make_event_problem", lambda *_: object())
    monkeypatch.setattr(predictive_linear, "select_entries", lambda *_: [dict(points=19)])
    monkeypatch.setattr(event_position, "refit", refit)
    decision, info = algo08_collapsed_linear.admit(payload, 12.5)
    assert calls == ["c0", "fitted_c"] and info["offered_points"] == 19
    assert (decision is not payload) == info["accepted"] == qualifies
    assert payload["arms"] is original and payload["entries"] == []
