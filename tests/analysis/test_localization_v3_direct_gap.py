"""Direct timing policy owns selection and gates without changing legacy recovery."""

from types import SimpleNamespace

import pytest

from leo.analysis.localization_v3 import gap_controller as gap
from leo.contracts.localization_v5 import direct_gap_policy


def case(gapped=True):
    ids = [f"p{i}" for i in range(13)]
    times = list(range(12)) + ([18] if gapped else [12])
    parent = dict(observation_ids=ids, times=times)
    context = dict(scan=SimpleNamespace(tracks=[parent]))
    inventory = dict(tracks=[dict(arm=arm, track_id="parent", track_index=0,
                                  current_large=True, observation_ids=ids,
                                  all_track_observation_ids=ids, component="radio")
                             for arm in gap.ARMS])
    return context, inventory, [dict(observation_id="old", time_s=0),
                                *[dict(observation_id=oid, time_s=t)
                                  for oid, t in zip(ids, times, strict=True)]]


def test_selector_requires_proper_matched_unowned_timing_component(monkeypatch):
    context, inventory, _ = case()
    owners = {arm: {"old": 10} for arm in gap.ARMS}
    expected = gap.direct_timing_targets(context, inventory, owners)
    assert len(expected) == 1 and expected[0]["points"] == 12
    assert expected[0]["parent_points"] == 13
    assert expected[0]["branch_id"] == "99d3910a50776a009ba3"
    context["scan"].tracks[0]["times"][-1] = 12
    assert gap.direct_timing_targets(context, inventory, owners) == []
    context, inventory, _ = case()
    owners["c0"]["p1"] = 20
    assert gap.direct_timing_targets(context, inventory, owners) == []
    owners["c0"].pop("p1")
    inventory["tracks"][1]["observation_ids"] = ["p0"]
    assert gap.direct_timing_targets(context, inventory, owners) == []


def test_no_gap_skips_prepare_and_all_numerical_stages(monkeypatch):
    context, inventory, observations = case(gapped=False)
    monkeypatch.setattr(gap, "prepare_gap", lambda *args: pytest.fail("no prepare"))
    result = gap.recover_gaps(context, inventory, observations, dict(attempts=[]), {},
        {arm: {"old": 10} for arm in gap.ARMS},
        run_stage=lambda *args: pytest.fail("no numerical stage"), clock=lambda: 0,
        direct_gap_policy=direct_gap_policy())
    assert result["policy"] == direct_gap_policy()
    assert result["targets"] == result["trials"] == result["stages"] == []
    assert result["candidate"] is result["selected"] is None
    legacy = gap.recover_gaps(context, inventory, observations, dict(attempts=[]), {},
        {arm: {"old": 10} for arm in gap.ARMS},
        run_stage=lambda *args: pytest.fail("no numerical stage"), clock=lambda: 0)
    assert {key: value for key, value in result.items() if key != "policy"} == legacy


def test_non_support_and_timeout_leave_incumbent_untouched(monkeypatch):
    context, inventory, observations = case()
    branch = gap.direct_timing_targets(context, inventory, {a: {"old": 10} for a in gap.ARMS})[0]
    source = dict(protocol=dict(parent_observation_ids=context["scan"].tracks[0]["observation_ids"]),
                  branches=[dict(branch_id=branch["branch_id"],
                                 observation_ids=context["scan"].tracks[0]["observation_ids"][:12])])
    monkeypatch.setattr(gap, "prepare_gap", lambda *args: source)
    monkeypatch.setattr(gap, "annotate_gap", lambda *args, **kwargs: (
        dict(result=dict(annotation=dict(status="insufficient_holdouts"))), {}))
    owners = {arm: {"old": 10} for arm in gap.ARMS}
    result = gap.recover_gaps(context, inventory, observations, dict(attempts=[]), {}, owners,
        run_stage=lambda name, op, cap: (True, op()), clock=lambda: 0,
        direct_gap_policy=direct_gap_policy())
    assert result["selected"] is None and len(result["excluded"]) == 1
    assert [row["name"] for row in result["stages"]] == [
        "gap-0-prepare", f"gap-0-{branch['branch_id']}-annotation"]
    timed = gap.recover_gaps(context, inventory, observations, dict(attempts=[]), {}, owners,
        run_stage=lambda name, op, cap: (_ for _ in ()).throw(TimeoutError("deadline")),
        clock=lambda: 0, direct_gap_policy=direct_gap_policy())
    assert timed["selected"] is None and timed["stages"] == []
    assert timed["excluded"] == [dict(budget_exhausted="deadline")]


def test_exact_branch_additions_and_parent_protection():
    ids = [f"p{i}" for i in range(12)]
    owners = {arm: {"old": 10} for arm in gap.ARMS}
    annotation = dict(result=dict(annotation=dict(norad=20)),
                      protocol=dict(target=dict(observation_ids=ids)))
    protocol = dict(matched_c_arms=True, phase_rounds=5, steps=48,
                    target_calibrates_receiver=False,
                    target_updates_unobserved_satellite_parameters=False,
                    original_noise_weights_and_priors=True,
                    conditional_satellite_refresh=True,
                    targets=[dict(observation_ids=ids, norad=20)])
    fit = dict(arms={arm: dict(proposed_owners={"old": 10, **dict.fromkeys(ids, 20)})
                     for arm in gap.ARMS})
    trial = dict(protocol=protocol, target_0=fit)
    gap.validate_direct_trial(trial, annotation, owners)
    fit["arms"]["c0"]["proposed_owners"]["p0"] = 99
    with pytest.raises(ValueError, match="ownership or branch additions"):
        gap.validate_direct_trial(trial, annotation, owners)
    fit["arms"]["c0"]["proposed_owners"]["p0"] = 20
    protocol["targets"][0]["observation_ids"] = ids[:-1]
    with pytest.raises(ValueError, match="independently annotated component"):
        gap.validate_direct_trial(trial, annotation, owners)


def test_selected_branch_runs_independent_gates_and_binds_training(monkeypatch):
    context, inventory, observations = case()
    owners = {arm: {"old": 10} for arm in gap.ARMS}
    selected = gap.direct_timing_targets(context, inventory, owners)[0]
    ids = context["scan"].tracks[0]["observation_ids"][:12]
    source = dict(protocol=dict(parent_observation_ids=context["scan"].tracks[0]["observation_ids"]),
                  branches=[dict(branch_id=selected["branch_id"], observation_ids=ids)])
    identity = dict(status="conditionally_supported_identity", norad=20, minimum_margin=50)
    training = SimpleNamespace(policy=dict(id="test-training"))
    annotation = dict(result=dict(annotation=identity, folds=[dict(seed=1)]),
                      protocol=dict(target=dict(observation_ids=ids),
                                    training_optimizer_policy=training.policy))
    protocol = dict(matched_c_arms=True, phase_rounds=5, steps=48,
                    target_calibrates_receiver=False,
                    target_updates_unobserved_satellite_parameters=False,
                    original_noise_weights_and_priors=True,
                    conditional_satellite_refresh=True,
                    targets=[dict(observation_ids=ids, norad=20)])
    fit = dict(paired_valid=True, target_entries=[dict(observation_ids=ids)],
               arms={arm: dict(proposed_owners={"old": 10, **dict.fromkeys(ids, 20)},
                               proposed_associated_ids=["old", *ids],
                               final_phase_change_s=0.001,
                               endpoint_latlon=[37.0, -122.0],
                               target_diagnostics=[dict(times_s=list(range(12)))])
                     for arm in gap.ARMS})
    trial = dict(protocol=protocol, target_0=fit)
    audit = dict(all_verified=True, rows=[dict(role=role, arm=arm, verified=True,
        exact_family_replays=[dict(all_gate_slacks=dict(rms=2.0))],
        phase_reference_check=dict(phase_change_s=0.001), incumbent_ownership_changes=[])
        for role in ("control", "target_0") for arm in gap.ARMS])
    calls = []
    monkeypatch.setattr(gap, "prepare_gap", lambda *args: source)
    monkeypatch.setattr(gap, "annotate_gap", lambda *args, **kwargs: (
        calls.append(kwargs) or annotation, dict(stage="annotation")))
    monkeypatch.setattr(gap, "require_distinct_annotation",
                        lambda result, plan: calls.append("distinct"))
    monkeypatch.setattr(gap, "shared_family_route",
                        lambda folds, norad: calls.append("shared") or True)
    monkeypatch.setattr(gap, "fit_gap", lambda *args: (trial, dict(stage="fit")))
    monkeypatch.setattr(gap, "audit_gap", lambda *args: (audit, dict(stage="audit")))
    states = []
    result = gap.recover_gaps(context, inventory, observations, dict(attempts=[]), {}, owners,
        run_stage=lambda name, op, cap: (True, op()), clock=lambda: 0,
        direct_gap_policy=direct_gap_policy(), annotation_training_fit=training,
        on_selection=states.append)
    assert calls == [dict(training_fit=training), "distinct", "shared"]
    assert result["selected"]["branch_id"] == selected["branch_id"]
    assert result["selected"]["qualification"]["added_points"] == dict(c0=12, fitted_c=12)
    assert states[0]["selection"]["kind"] == "gap_conditional"
    assert states[0]["owners"]["c0"] == fit["arms"]["c0"]["proposed_owners"]
