import pytest

from leo.api.graph_position_lookup_v6 import GraphPositionLookupV6, completed_view
from leo.contracts.fast_graph_position_v6 import MODEL_VERSION
from leo.storage.graph_position_lookup_v5 import completed_view as previous_completed_view


def terminal():
    position = dict(latitude_deg=37., longitude_deg=-122.)
    arms = {a: dict(endpoint_latlon=[37., -122.]) for a in ("c0", "fitted_c")}
    v1 = dict(model_version="algo02-causal-family-v1", state="complete",
              position=position, arms=arms)
    v2 = dict(model_version="algo03-causal-predictive-v1", state="complete", position=position,
              baseline=v1, selected=dict(arms=arms), decision="ALGO03_single", baseline_seconds=1)
    v3 = dict(model_version="algo04-causal-numerical-v1", state="complete", position=position,
              incumbent=v2, candidate=v2, decision="ALGO04_additive", numerical_seconds=1)
    v4 = dict(model_version="algo05-causal-gap-conditional-v1", state="complete", position=position,
              incumbent=v3, candidate=dict(trial=dict(arms=arms)), decision="ALGO05_additive")
    v5 = dict(model_version="algo06-causal-residual-family-v1", state="complete", position=position,
              incumbent=v4, candidate=dict(trial=dict(arms=arms)), decision="ALGO06_additive",
              incumbent_seconds=3, recovery_seconds=2, total_seconds=5)
    new_arms = {a: dict(endpoint_latlon=[38., -123.], rms_hz=1.5, objective=2.5)
                for a in ("c0", "fitted_c")}
    return dict(model_version=MODEL_VERSION, state="complete", incumbent=v5,
                position=dict(latitude_deg=38., longitude_deg=-123.),
                candidate=dict(arms=new_arms), decision="ALGO07_reassociation",
                incumbent_seconds=5, recovery_seconds=2, total_seconds=7)


def test_completed_hit_uses_only_validated_lookup_port():
    saved = terminal()

    class Lookup:
        def completed_run(self, run):
            assert run == "scan"
            return saved

    class Forbidden:
        def detail(self, _):
            raise AssertionError("Upstream enumeration must not run for completed hit")

    reader = GraphPositionLookupV6(".", MODEL_VERSION, lookup=Lookup(), previous=Forbidden())
    view = reader.detail("scan")
    assert view["selected_model"] == MODEL_VERSION
    assert view["selected"]["model_version"] == MODEL_VERSION
    assert view["selected"]["arms"] == saved["candidate"]["arms"]
    assert view["position"] == saved["position"]
    assert view["decision"] == "ALGO07_reassociation" and not view["fallback"]


@pytest.mark.parametrize("prior_decision", ["ALGO06_additive", "ALGO05_fallback"])
def test_fallback_preserves_exact_published_selection_and_endpoint(prior_decision):
    saved = terminal()
    saved["incumbent"]["decision"] = prior_decision
    saved.update(candidate=None, decision="ALGO06_fallback",
                 position=saved["incumbent"]["position"])
    view = completed_view("scan", saved)
    old = previous_completed_view("scan", saved["incumbent"])
    assert view["selected"] == old["selected"]
    assert view["position"] == old["position"]
    assert view["baseline"] == old["baseline"] and view["incumbent"] == old["incumbent"]
    assert view["decision"] == "ALGO06_fallback" and view["fallback"]


def test_missing_v6_calls_v5_public_lookup():
    calls = []

    class Missing:
        def completed_run(self, _):
            return None

    class Previous:
        def detail(self, run):
            calls.append(run)
            return dict(state="complete", selected=dict(model_version="actual-incumbent"),
                        decision="ALGO06_additive",
                        position={"latitude_deg": 37., "longitude_deg": -122.})

    reader = GraphPositionLookupV6(".", MODEL_VERSION, lookup=Missing(), previous=Previous())
    view = reader.detail("scan")
    assert calls == ["scan"] and view["fallback"]
    assert view["selected"]["model_version"] == "actual-incumbent"
    assert "Awaiting qualified ALGO07" in view["reason"]
    with pytest.raises(ValueError):
        reader.detail("../escape")
