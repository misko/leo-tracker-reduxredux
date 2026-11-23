from pathlib import Path
import sys
from types import SimpleNamespace

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "reports/ALGO08/v3"))

from pre_signed_hybrid import ARMS, binding, eligible, family_witnesses, interior_pair, signed_refitter


def record(point):
    return dict(endpoint_east_north_km=point, endpoint_latlon=point,
                negative_twice_elbo=23., RMS_hz=5., final_phase_change_s=.005,
                gates=dict(tracks=[dict(compatible=True)]), linear_gates=[dict(compatible=True)])


def stage():
    region = SimpleNamespace(half_width_km=12.5)
    tracks = [dict(key="a", times=range(4)), dict(key="skip", times=range(12)),
              dict(key="b", times=range(2)), dict(key="c", times=range(3))]
    rows = [dict(component=track["key"], candidate_index=index, active_curvature=active)
            for track, index, active in zip(tracks, (0, 1, 0, 1), (True, False, True, True), strict=True)]
    scan = SimpleNamespace(tracks=tracks, search_region=region, norads=[12345, 23456, 34567])
    node = dict(seed=dict(rows=rows))
    relation = dict(final_node=node)
    arms = {"c0": record([1., 3.]), "fitted_c": record([1.4, 3.5])}
    family = dict(policy_arms=arms, linear_paired_valid=True, linear_entries=[dict(candidate_index=0)],
                  mask=np.array([True]*4 + [True, False] + [True]*3), confidence=[.96, .97, .95])
    return scan, relation, family


def test_witnesses_use_named_curved_order_and_only_intact_fragments():
    scan, conservative, family = stage()
    result = family_witnesses(scan.tracks, conservative["final_node"], family["mask"], family["confidence"],
                              family["linear_entries"])
    assert result == {0: .96, 1: .95}
    audit = {}
    assert eligible(scan, conservative, family, audit) is None
    assert audit["family_confidence"] == [[12345, .96], [23456, .95]]
    family["mask"][3] = False
    assert eligible(scan, conservative, family, {}) == "insufficient_family_witness"


def test_missing_predictive_family_witness_uses_named_tail():
    scan, conservative, family = stage()
    family["linear_entries"].append(dict(candidate_index=2))
    audit = {}
    assert eligible(scan, conservative, family, audit) == "insufficient_family_witness"
    assert audit["families_without_strong_intact_witness"] == 1
    family["mask"] = family["mask"][:-1]
    assert eligible(scan, conservative, family, {}) == "unrecognized_named_curved_layout"


@pytest.mark.parametrize("unsafe", ("boundary", "separation", "nonfinite", "predictive"))
def test_two_arm_guard_declines_unsafe_points(unsafe):
    scan, _, family = stage()
    arms = family["policy_arms"]
    if unsafe == "boundary":
        arms["fitted_c"]["endpoint_east_north_km"] = [11., 3.]
    if unsafe == "separation":
        arms["fitted_c"]["endpoint_east_north_km"] = [9., 3.]
    if unsafe == "nonfinite":
        arms["fitted_c"]["negative_twice_elbo"] = np.nan
    if unsafe == "predictive":
        arms["fitted_c"]["linear_gates"][0]["compatible"] = False
    assert not interior_pair(arms, scan.search_region)


@pytest.mark.parametrize("failed", (False, True))
def test_paired_signed_warm_does_not_commit_one_arm_before_the_second(failed):
    scan, conservative, family = stage()
    node, keep, entries = conservative["final_node"], family["mask"], family["linear_entries"]
    warmed, original, audit = [], [], {}
    powers, means, model = object(), object(), object()

    def warm(candidate, offered, arm):
        warmed.append(arm)
        assert candidate["arms"] is family["policy_arms"]
        assert offered is means and candidate["keep"] is keep and candidate["entries"] is entries
        return (None, "unsettled") if failed and arm == "fitted_c" else (record([3., 4.]), None)

    def cold(*args):
        original.append(args[3])
        return record([2., 3.])

    refit = signed_refitter(cold, family["policy_arms"], audit, warm=warm)
    first = refit(scan, node, keep, "c0", powers, means, model, [], entries)
    assert warmed == list(ARMS)
    second = refit(scan, node, keep, "fitted_c", powers, means, model, [], entries)
    assert [first["endpoint_latlon"], second["endpoint_latlon"]] == [[2., 3.] if failed else [3., 4.]]*2
    assert original == (list(ARMS) if failed else [])
    assert audit["warm_used"] is not failed


@pytest.mark.parametrize("incomplete", (False, True))
def test_causal_finish_bypasses_alternatives_only_for_full_evidence(monkeypatch, incomplete):
    from leo.analysis.localization_v3 import family_cavity, signed_context
    from tools import algo08_position
    from tools.pipeline_eval.variants import v5_core

    scan, conservative, family = stage()
    selected, nominated = [], []
    model = dict(arms=family["policy_arms"], signed=dict(selection=dict(qualified=False), accepted=False))
    audit = {}

    def nominate(_):
        nominated.append(True)
        return dict(status="complete", families=[])

    def named(prepared, region, bound, stages, *, selected_evidence):
        candidate = signed_context.signed_context(scan, conservative, family)
        family_cavity.nominate_families(candidate)
        selected_evidence(prepared, candidate, None)
        return dict(status="ok", source="original")

    def standard(prepared, candidate, fit):
        assert candidate is model and fit is None
        selected.append(True)
        return dict(position_grid=dict(complete=not incomplete or len(selected) > 1))

    monkeypatch.setattr(v5_core, "infer", named)
    monkeypatch.setattr(signed_context, "signed_context", lambda *args, **kwargs: model)
    monkeypatch.setattr(algo08_position, "selected_packet", standard)
    monkeypatch.setattr(family_cavity, "nominate_families", nominate)
    with binding(True, audit):
        result = v5_core.infer({}, scan.search_region, object(), {},
                               selected_evidence=lambda *args: algo08_position.selected_packet(*args))
    if incomplete:
        assert result["source"] == "original"
        assert selected == [True, True] and nominated == [True]
        assert audit["signed"][0]["route"] == "retry_full_named_after_evidence"
        assert "full_named_fallback" in audit["signed"][0]
    else:
        assert result["metrics"]["original_alternatives_evaluated"] is False
        assert result["metrics"]["cavity_offered"] is None
        assert list(result["arms"]) == list(ARMS)
        assert selected == [True] and nominated == []
        assert audit["signed"][0]["route"] == "fixed_named_roster"


@pytest.mark.parametrize("warm_fails", (False, True))
def test_qualified_signed_prior_keeps_actual_reference_inputs_and_bills_named_fallback(monkeypatch, warm_fails):
    import lighter_joint_estimator
    from leo.analysis.localization_v3 import family_cavity, signed_context
    from tools import algo08_position
    from tools.pipeline_eval.variants import v5_core

    scan, conservative, family = stage()
    powers, exact_signed_means, model = object(), object(), object()
    warm_order, cold_order, nominated = [], [], []
    audit, choices = {}, {}

    def routed(*args):
        cold_order.append(args[3])
        assert args[5] is exact_signed_means
        return record([3., 3.])

    def warm(candidate, means, arm):
        assert means is exact_signed_means
        assert candidate["arms"] is family["policy_arms"]
        assert candidate["entries"] is family["linear_entries"]
        warm_order.append(arm)
        return ((None, "did_not_settle") if warm_fails and arm == "c0" else (record([4., 4.]), None))

    def condition(*args, **kwargs):
        arms = {arm: signed_context.refit(scan, conservative["final_node"], family["mask"], arm,
                                         powers, exact_signed_means, model, [], family["linear_entries"])
                for arm in ARMS}
        return dict(arms=arms, signed=dict(selection=dict(qualified=True), accepted=True))

    def nominate(_):
        nominated.append(True)
        return dict(status="complete", families=[])

    def named(prepared, region, bound, states, *, selected_evidence):
        candidate = signed_context.signed_context(scan, conservative, family)
        family_cavity.nominate_families(candidate)
        selected_evidence(prepared, candidate, None)
        return dict(status="ok")

    def render(_prepared, candidate, fit):
        assert fit is None
        choices.update(candidate["arms"])
        return dict(position_grid=dict(complete=True))

    monkeypatch.setattr(signed_context, "refit", routed)
    monkeypatch.setattr(signed_context, "signed_context", condition)
    monkeypatch.setattr(lighter_joint_estimator, "warm_arm", warm)
    monkeypatch.setattr(family_cavity, "nominate_families", nominate)
    monkeypatch.setattr(v5_core, "infer", named)
    monkeypatch.setattr(algo08_position, "selected_packet", render)
    with binding(True, audit):
        v5_core.infer({}, scan.search_region, object(), {},
                      selected_evidence=lambda *args: algo08_position.selected_packet(*args))
    assert warm_order == list(ARMS)
    assert cold_order == (list(ARMS) if warm_fails else [])
    assert nominated == ([True] if warm_fails else [])
    assert [choices[arm]["endpoint_latlon"] for arm in ARMS] == ([[3., 3.]] if warm_fails else [[4., 4.]])*2
    state = audit["signed"][0]
    assert state["signed_qualified"] and state["signed_adopted"]
    assert state["warm_signed"]["warm_used"] is not warm_fails
