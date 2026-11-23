from pathlib import Path
import sys
from types import SimpleNamespace

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "reports/ALGO08/v3"))

import isolated_salvage as rescue


def local_failure(feature, profile=True):
    shape = dict(mean_z=.3, slope_z=1., maximum_step_z=2., quadratic_bic_gain=-12., lag1_acf=-.1)
    failed = dict(shape, **{feature: 5.})
    return dict(compatible=False, profile_rms_hz=120., profile_bias_hz=100., minimum_elevation_deg=10.,
                aliases_changed=0, points=48, profile_diagnostics=failed if profile else shape,
                conditional_residual_gate=dict(rms_hz=120., compatible=False, diagnostics=failed))


def test_slope_offer_requires_both_original_shape_checks_and_all_other_limits():
    gate = local_failure("slope_z")
    assert rescue.sole_failure(gate, "slope_z", permit_clear_profile=False)
    assert not rescue.sole_failure(gate, "maximum_step_z", permit_clear_profile=True)
    gate["profile_diagnostics"] = dict(gate["profile_diagnostics"], lag1_acf=-.8)
    assert not rescue.sole_failure(gate, "slope_z", permit_clear_profile=False)
    step = local_failure("maximum_step_z", profile=False)
    assert rescue.sole_failure(step, "maximum_step_z", permit_clear_profile=True)
    assert not rescue.sole_failure(step, "maximum_step_z", permit_clear_profile=False)
    step["aliases_changed"] = 1
    assert not rescue.sole_failure(step, "maximum_step_z", permit_clear_profile=True)


def node(label_a, label_b):
    return dict(seed=dict(rows=[dict(component="wanted", candidate_norad=label_a, candidate_index=0),
                                dict(component="unrelated", candidate_norad=label_b, candidate_index=1)]),
                aliases=[1, -1] if label_b == 33 else [1, 0])


def test_isolate_restores_nonadmitted_reassigned_rows_and_aliases():
    before, after = node(10, 33), node(10, 17)
    after["seed"]["rows"][0]["mark"] = [1]
    chosen = rescue.isolate_node(before, after, {"wanted"})
    assert chosen["aliases"] == [1, -1]
    assert chosen["seed"]["rows"][1] == before["seed"]["rows"][1]
    chosen["seed"]["rows"][0]["mark"].append(2)
    assert after["seed"]["rows"][0]["mark"] == [1]
    with pytest.raises(ValueError, match="component order"):
        rescue.isolate_node(before, after, {"unbound"})


def prepared_problem(n, mask):
    t = [dict(key=key, observation_ids=[f"{key}-{k}" for k in range(4)])
         for key in ("wanted", "unrelated")]
    return SimpleNamespace(rows=n["seed"]["rows"], members=[0, 1], slices=[slice(0, 4), slice(4, 8)],
                           alias=n["aliases"], scan=SimpleNamespace(tracks=t), keep=mask, diagnostic_node=n)


def complete_offer(key="wanted", index=0, norad=10, alias=1):
    return dict(component=key, selected=dict(points=4, start_index=0, stop_index=4,
                candidate_index=index, norad=norad, alias=alias, phase_s=.4))


def test_qualifying_reads_live_signed_support_and_declines_changed_identity_or_alias(monkeypatch):
    original, updated = node(10, 33), node(10, 17)
    initial = np.zeros(8, bool)
    expanded = np.ones(8, bool)
    first, current = prepared_problem(original, expanded), prepared_problem(updated, expanded)

    def profiles(problem, point, keys):
        assert keys == {"wanted"}
        return {"wanted": dict(ids=np.array(problem.scan.tracks[0]["observation_ids"]), mask=np.ones(4, bool))}

    monkeypatch.setattr(rescue, "state", profiles)
    monkeypatch.setattr(rescue, "local_gate", lambda *_: local_failure("slope_z"))
    source = [complete_offer(), complete_offer("unrelated", 1, 17, 0)]
    actual, census = rescue.qualifying(first, current, [0., 0.], expanded, initial, initial, source)
    assert [row["component"] for row in actual] == ["wanted"]
    assert census == dict(signed_contiguous_offers=2, intact_same_identity_alias=1)
    first.alias = [9, -1]
    assert rescue.qualifying(first, current, [0., 0.], expanded, initial, initial, source)[0] == []


@pytest.mark.parametrize("eligible_count", [1, 2])
def test_trial_has_one_paid_fit_on_exact_mask_or_declines_an_ambiguous_offer(monkeypatch, eligible_count):
    before, after = node(10, 33), node(10, 17)
    initial = np.zeros(8, bool)
    survivors = initial.copy()
    expanded = np.ones(8, bool)
    a, b = prepared_problem(before, expanded), prepared_problem(after, expanded)
    if eligible_count == 1:
        survivors[4:] = True
    nominate = complete_offer()["selected"]
    trials = [dict(component="wanted", ids=a.scan.tracks[0]["observation_ids"], original_nomination=nominate)]
    trials *= eligible_count
    monkeypatch.setattr(rescue, "qualifying", lambda *args: (trials, {}))
    audit, seen = {}, []
    scan = SimpleNamespace(search_region=SimpleNamespace(half_width_km=12.5))
    point = np.array([0., 0.])

    def build(scan, new, keep, point, prior, model):
        seen.append(("build", keep.tolist(), prior.copy()))
        out = prepared_problem(new, keep.copy())
        out.calculate = lambda x: {"negative_twice_elbo": 100. - x[0]}
        return out, object(), object()

    def fit(problem, start, *, iterations):
        assert iterations == 48
        seen.append(("fit", problem.keep.tolist()))
        return dict(parameters=np.asarray([1., 1.]))

    metrics = lambda model, point: dict(tracks=[dict(component="wanted", compatible=True)])
    result = rescue.refine((a, {}), scan, after, b, initial, expanded, survivors, point, {},
                           dict(past_distribution_qualified=True, salvage=[complete_offer()]),
                           audit, build=build, fit=fit, metrics=metrics, reserve=lambda: True)
    if eligible_count == 1:
        assert result[0].tolist() == [True]*8
        assert seen == [("build", [True]*8, {0: .4}), ("fit", [True]*8)]
        assert audit["status"] == "curved_gate_passed" and audit["fit_calls"] == 1
    else:
        assert result is None and not seen and audit["fit_calls"] == 0


def test_local_target_must_pass_even_if_its_failure_resembles_a_pending_endpoint():
    mask = np.ones(8, bool)
    p = prepared_problem(node(10, 33), mask)
    gate = [dict(component="wanted", compatible=False), dict(component="unrelated", compatible=True)]
    assert rescue.provisional_gate(p, np.zeros(2), dict(tracks=gate), "wanted", mask, {}) == "original_target_curved_gate"


@pytest.mark.parametrize("passes", [True, False])
def test_composed_endpoint_uses_one_shared_attempt_and_no_provisional_broad_pruning(monkeypatch, passes):
    import blind_joint_finish as finish
    import blind_joint_repair as repair
    import endpoint_track_repair as endpoint

    original_calls = []
    endpoint_calls = []
    scan, region, original_node, isolated_node = object(), object(), object(), object()
    problem = SimpleNamespace(scan=scan, diagnostic_node=isolated_node)
    failure = dict(component="surviving", observation_ids=["a", "b"], compatible=False,
                   conditional_residual_gate=dict(compatible=False, diagnostics=dict(maximum_step_z=4.2)))
    arms = {arm: dict(gates=dict(tracks=[failure]), linear_gates=[]) for arm in endpoint.ARMS}
    first = dict(arms=arms)
    trimmed = dict(arms={arm: {} for arm in endpoint.ARMS})
    audited = dict(isolated_branch=True, target=dict(component="new", original_nomination={"norad": 333}))

    def first_pair(scan, node, keep, base, powers, means, model, entries, point, region, detail):
        assert node is isolated_node and detail is audited
        detail["finish"] = {"original": 1}
        return first, False

    def attempt(candidate, failed, region, audit):
        endpoint_calls.append(failed["c0"]["component"])
        audit["status"] = "accepted" if passes else "rejected"
        return trimmed if passes else None

    def ordinary(candidate, region, detail):
        original_calls.append(candidate)
        return candidate, None

    monkeypatch.setattr(finish, "finish_pair", first_pair)
    monkeypatch.setattr(finish, "readout", lambda row: row)
    monkeypatch.setattr(repair, "repair_once", ordinary)
    monkeypatch.setattr(endpoint, "try_trim", attempt)
    with rescue.binding():
        after, accepted = finish.finish_pair(scan, original_node, np.ones(2, dtype=bool), problem,
                                             None, None, None, [], np.zeros(2), region, audited)
        assert accepted is passes and after is (trimmed if passes else first)
        assert not original_calls
        if not passes:
            assert repair.repair_once(first, region, {}) == (first, None)
            assert original_calls == [first]
    assert endpoint_calls == ["surviving"]
