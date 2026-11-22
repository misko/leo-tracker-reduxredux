import pytest

from leo.analysis.localization_v3 import signed_context
from tools.pipeline_eval.variants import algo08_collapsed, algo08_collapsed_salvage
from tools.pipeline_eval.variants import algo08_collapsed_signed_finish as finish


@pytest.mark.parametrize("accepted", (False, True))
def test_signed_finish_uses_current_causal_history_and_only_adopts_a_passing_pair(monkeypatch,
                                                                              accepted):
    before = {key: object() for key in ("scan", "node", "keep", "powers", "model", "means", "arms")}
    before["entries"] = [{"component": "line"}]
    raw, released = {"sources": [1, 2]}, {"strictly_pre_RF": True, "GPS_or_radio_used": False}
    prepared = dict(phase_history=raw, phase_forecast=released, tracks={"observations": [3]},
                    sky={"metadata": {"cutoff_utc_ns": 42}})
    digest = algo08_collapsed.digest(raw)
    means, arms = object(), object()

    def paired(scan, original, family, source, forecast, observations, **metadata):
        assert scan is before["scan"] and original == {"final_node": before["node"]}
        assert family == dict(
            status="accepted", mask=before["keep"], weights=before["powers"],
            hyperparameters_from_pre_RF_TLE_only=before["model"],
            linear_entries=before["entries"], linear_paired_valid=True, policy_arms=before["arms"],
        )
        assert source is raw and forecast == dict(released, history_sha256=digest)
        assert observations is prepared["tracks"]["observations"]
        assert metadata == dict(case="SCAN", cutoff_utc_ns=42, history_sha256=digest)
        return dict(signed={"accepted": accepted}, means=means, arms=arms)

    monkeypatch.setattr(signed_context, "signed_context", paired)
    result, decision = finish.apply_signed(prepared, before)
    assert decision["accepted"] is accepted
    assert result == (dict(before, arms=arms, means=means) if accepted else before)
    if not accepted:
        assert result is before
    assert "history_sha256" not in released


def test_rejects_stale_forecast_binding_before_fit(monkeypatch):
    monkeypatch.setattr(signed_context, "signed_context", lambda *_: pytest.fail("unexpected fit"))
    prepared = dict(phase_history={}, phase_forecast={"history_sha256": "wrong"})
    with pytest.raises(ValueError, match="phase history has changed"):
        finish.apply_signed(prepared, {})


def test_scopes_update_between_recovery_and_publication(monkeypatch):
    prepared, collapsed, signed = object(), object(), object()
    observed = []

    def recover(incumbent, width, **options):
        assert width == 12.5 and options == {"repair": True}
        observed.append("recover")
        return collapsed, {"trimmed": 4}

    def apply(data, selected):
        assert data is prepared and selected is collapsed
        observed.append("sign")
        return signed, {"accepted": True, "selection": {"qualified": True}}

    def infer(data, *, selected_evidence):
        current, metrics = algo08_collapsed_salvage.recover(collapsed, 12.5, repair=True)
        selected_evidence(current)
        return metrics

    def guard_and_publish(current):
        assert current is signed
        observed.append("guard_and_publish")
        raise ValueError("publication stopped")

    monkeypatch.setattr(algo08_collapsed, "infer", infer)
    monkeypatch.setattr(algo08_collapsed_salvage, "recover", recover)
    monkeypatch.setattr(finish, "apply_signed", apply)
    with pytest.raises(ValueError, match="publication stopped"):
        with finish.signed_finish():
            algo08_collapsed.infer(prepared, selected_evidence=guard_and_publish)
    assert observed == ["recover", "sign", "guard_and_publish"]
    assert algo08_collapsed.infer is infer and algo08_collapsed_salvage.recover is recover
