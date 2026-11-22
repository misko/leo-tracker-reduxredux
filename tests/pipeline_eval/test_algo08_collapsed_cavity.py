from types import SimpleNamespace

import pytest

from leo.analysis.localization_v3 import family_cavity, signed_context
from tools.pipeline_eval.variants import algo08_collapsed_cavity as variant


def arms(lat):
    return {arm: dict(endpoint_latlon=[lat, 10.0], RMS_hz=11.0,
                      phase_reference=[0.0], state={}) for arm in ("c0", "fitted_c")}


@pytest.mark.parametrize("gain, accepted", [(0, False), (1, False), (1, True)])
def test_stock_policy_uses_selected_rich_context_before_guard(monkeypatch, gain, accepted):
    incumbent = dict(scan=SimpleNamespace(norads=(3, 5, 12)), node={}, model={},
                     keep=[True], powers=[1.0], means=[0.0], entries=[], arms=arms(51.0))
    full = dict(incumbent, all_means=[0.0] * 3, observations=object())
    replacement_arms = arms(51.01)
    calls = []
    offer = dict(original_norad=5, best={"norad": 12}, predictive_gain=gain)
    nominations = dict(status="complete", families=[offer])
    trial = dict(replacements=[{"norad": 12}], paired_valid=accepted)
    fit = dict(status="complete", accepted=accepted, trials=[trial],
               selected=trial if accepted else None,
               policy_arms=replacement_arms if accepted else incumbent["arms"])

    def scan_context():
        calls.append("signed")
        return full

    def nominate(context):
        calls.append("nominate")
        assert context is full
        return nominations

    def select(context, offered):
        calls.append("fit")
        assert context is full and offered is nominations
        return fit

    def collapsed(data, _region, _bound, _stages, *, selected_evidence):
        assert signed_context.signed_context() is full
        selected_evidence(data, incumbent, None)
        return dict(status="ok", arms=variant.arm_readout(incumbent["arms"]), metrics={})

    def guard(data, signed, proposal):
        calls.append("guard")
        assert data == "prepared" and signed is full
        assert proposal is (fit if gain else None)

    monkeypatch.setattr(signed_context, "signed_context", scan_context)
    monkeypatch.setattr(family_cavity, "nominate_families", nominate)
    monkeypatch.setattr(family_cavity, "cavity_policy", select)
    outcome = variant.with_cavity(collapsed)("prepared", None, None, {}, selected_evidence=guard)
    assert calls == ["signed", "nominate", *(["fit"] if gain else []), "guard"]
    assert outcome["metrics"]["complete_family_cavity"]["accepted"] is accepted
    expected = replacement_arms if accepted else incumbent["arms"]
    assert outcome["arms"] == variant.arm_readout(expected)
    assert signed_context.signed_context is scan_context


def test_rejects_a_context_with_different_selected_mask():
    incumbent = dict(scan=object(), node={}, model={}, keep=[False], powers=[1.0], means=[0.0])
    with pytest.raises(ValueError, match="lacks the selected signed incumbent"):
        variant.validate_context(dict(incumbent, keep=[True]), incumbent)
