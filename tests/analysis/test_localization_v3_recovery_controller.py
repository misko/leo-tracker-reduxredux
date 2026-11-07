from copy import deepcopy

import pytest

from leo.analysis.localization_v3 import recovery_controller as controller


def setup(monkeypatch, *, shared=False):
    targets = [
        dict(track_id=f"t{i}", observation_ids=[f"n{i}"], inactive_fragment=False) for i in range(2)
    ]
    inventory = dict(
        summary=[], policy={a: dict(proposed_associated_ids=["old"]) for a in controller.ARMS}
    )
    evidence = dict(
        inventory=inventory,
        publication_support={a: dict(owners={"old": 1}) for a in controller.ARMS},
        selected_targets=targets,
        eligible_targets=2,
    )
    monkeypatch.setattr(
        controller,
        "annotate",
        lambda d, inv, tid, **kw: dict(result=dict(folds=[tid]), protocol={}),
    )
    monkeypatch.setattr(
        controller,
        "identity_consensus",
        lambda folds, **kw: dict(
            status="conditionally_supported_identity", norad=2 + int(folds[0][-1])
        ),
    )
    monkeypatch.setattr(controller, "require_distinct_annotation", lambda *a: None)
    monkeypatch.setattr(controller, "shared_family_route", lambda *a: shared)

    def fit(d, inv, annotations, **kw):
        return dict(index=int(annotations[0]["result"]["folds"][0][-1]))

    monkeypatch.setattr(controller, "fit_new", fit)
    monkeypatch.setattr(controller, "fit_shared", fit)
    monkeypatch.setattr(controller, "audit_inclusion", lambda *a, **kw: {})

    def candidate(inv, trial, audit, is_shared):
        i = trial["index"]
        entry = dict(observation_ids=[f"n{i}"], norad=i + 2)
        return dict(
            kind="shared_family" if is_shared else "new_family",
            targets=[entry],
            arms={
                a: dict(added_points=1, owners={"old": 1, f"n{i}": i + 2}) for a in controller.ARMS
            },
        )

    monkeypatch.setattr(controller, "single_candidate", candidate)
    return evidence


def execute(name, operation):
    return True, operation()


@pytest.mark.parametrize('shared', [False, True])
def test_inclusion_executor_keeps_target_order_and_reaches_retry(monkeypatch, shared):
    evidence = setup(monkeypatch, shared=shared)
    mapper, calls = object(), []

    def fit(d, inv, annotations, **kwargs):
        assert kwargs['map_arms'] is mapper
        index = int(annotations[0]['result']['folds'][0][-1])
        calls.append((index, kwargs.get('optimizer', 'lbfgsb')))
        return dict(index=index, control={}, new_family={})

    monkeypatch.setattr(controller, 'fit_shared', fit)
    monkeypatch.setattr(controller, 'fit_new', fit)
    monkeypatch.setattr(controller, 'single_candidate', lambda *a: None)
    monkeypatch.setattr(controller, 'numerical_only', lambda *a: True)
    controller.recover_tracks({}, evidence, run_stage=execute, discovery_allowed=lambda: True,
                              map_inclusion_arms=mapper)
    assert calls == ([(0, 'lbfgsb'), (1, 'lbfgsb')] if shared else
                     [(0, 'lbfgsb'), (0, 'powell'), (1, 'lbfgsb'), (1, 'powell')])


@pytest.mark.parametrize('port,argument', [
    ('map_annotation_folds', 'map_folds'), ('map_annotation_training', 'map_training'),
])
def test_fold_executor_is_forwarded_without_reordering_target_decisions(
    monkeypatch, port, argument
):
    evidence = setup(monkeypatch, shared=True)
    mapper, calls = object(), []

    def annotate(d, inv, tid, **kwargs):
        assert kwargs[argument] is mapper
        calls.append(tid)
        return dict(result=dict(folds=[tid]), protocol={})

    monkeypatch.setattr(controller, "annotate", annotate)
    result = controller.recover_tracks(
        {},
        evidence,
        run_stage=execute,
        discovery_allowed=lambda: True,
        **{port: mapper},
    )
    assert calls == ["t0", "t1"]
    assert result["selected"]["targets"][0]["norad"] == 2


def test_selected_checkpoint_preserves_exact_trial_and_cannot_mutate_decision(monkeypatch):
    evidence = setup(monkeypatch, shared=True)
    states = []
    result = controller.recover_tracks(
        {}, evidence, run_stage=execute, discovery_allowed=lambda: True, on_selection=states.append
    )
    assert len(states) == 1
    state = states[0]
    assert state["selection"] == dict(kind="shared_family", trial=dict(index=0))
    assert state["owners"] == {a: {"old": 1, "n0": 2} for a in controller.ARMS}
    state["arms"]["c0"]["owners"]["old"] = 99
    assert result["selected"]["arms"]["c0"]["owners"]["old"] == 1


def test_no_addition_checkpoint_is_the_original_published_support(monkeypatch):
    evidence = setup(monkeypatch, shared=True)
    states = []
    result = controller.recover_tracks(
        {}, evidence, run_stage=execute, discovery_allowed=lambda: False, on_selection=states.append
    )
    assert result["selected"] is None
    assert states[0]["selection"] is None
    assert states[0]["arms"] == evidence["inventory"]["policy"]
    assert states[0]["owners"] == {a: {"old": 1} for a in controller.ARMS}


def test_checkpoint_sink_failure_is_not_hidden_as_scientific_fallback(monkeypatch):
    evidence = setup(monkeypatch, shared=True)

    def fail(state):
        raise RuntimeError("checkpoint storage failed")

    with pytest.raises(RuntimeError, match="checkpoint storage failed"):
        controller.recover_tracks(
            {}, evidence, run_stage=execute, discovery_allowed=lambda: True, on_selection=fail
        )


def test_omitted_targets_are_explicit_and_first_qualified_is_retained(monkeypatch):
    evidence = setup(monkeypatch, shared=True)
    allowed = iter([False, True])
    result = controller.recover_tracks(
        {}, evidence, run_stage=execute, discovery_allowed=lambda: next(allowed)
    )
    assert [r["status"] for r in result["attempts"]] == [
        "discovery_budget_exhausted",
        "RF_qualified",
    ]
    assert result["selected"]["targets"][0]["norad"] == 3
    assert result["decision"] == "ALGO03_single"


def test_failed_stage_preserves_earlier_qualified_addition(monkeypatch):
    evidence = setup(monkeypatch, shared=True)

    def stages(name, operation):
        return (False, None) if name == "target-1-audit" else execute(name, operation)

    result = controller.recover_tracks(
        {}, evidence, run_stage=stages, discovery_allowed=lambda: True
    )
    assert result["attempts"][1]["status"] == "audit_execution_failed"
    assert result["selected"]["targets"][0]["norad"] == 2


@pytest.mark.parametrize('parallel', [False, True])
@pytest.mark.parametrize('paired', [False, True])
def test_joint_numerical_retry_refits_both_arms_and_all_three_methods(
        monkeypatch, parallel, paired):
    evidence = setup(monkeypatch)
    calls = []
    audit_calls, mapper = [], object()
    monkeypatch.setattr(controller, "probe_joint", lambda *a: {})

    def fit(d, probe, arm, method, optimizer):
        calls.append((optimizer, method, arm))
        success = not (optimizer == "lbfgsb" and method == "control" and arm == "fitted_c")
        return dict(
            protocol=dict(method=method, arm=arm),
            result=dict(
                history=[dict(success=success)],
                endpoint_east_north_km=[0, 0],
                endpoint_latlon=[37, -122],
                negative_twice_elbo=100,
            ),
        )

    def audit(d, inv, trial, control, **kwargs):
        assert kwargs == ({'map_batches': mapper} if parallel else {})
        audit_calls.append((trial['protocol']['method'], trial['protocol']['arm']))
        success = trial["result"]["history"][-1]["success"]
        return dict(
            RF_qualified_arm=success,
            owners={"old": 1, "n0": 2, "n1": 3},
            incumbent_owner_changes=[],
            phase_check=dict(phase_change_s=0.001),
            exact_incumbent_orbits=[dict(all_pass=True)],
            checks=dict(incumbent_and_numerical=success, target_gates=True),
        )

    monkeypatch.setattr(controller, "fit_joint", fit)
    monkeypatch.setattr(controller, "audit_joint", audit)
    states = []
    result = controller.recover_tracks(
        {}, evidence, run_stage=execute, discovery_allowed=lambda: True, on_selection=states.append,
        **({'map_joint_batches': mapper} if parallel else {}),
        **({'map_joint_arms': lambda fn, arms: [fn(arm) for arm in arms]} if paired else {})
    )
    assert len(calls) == 12
    assert audit_calls == [(method, arm) for _, method, arm in calls]
    assert result["decision"] == "ALGO03_joint"
    assert result["selected"]["arms"]["c0"]["added_points"] == 2
    assert result["selected"]["arms"]["c0"]["owners"] == {"old": 1, "n0": 2, "n1": 3}
    assert states[0]["selection"]["kind"] == "joint"
    assert set(states[0]["selection"]["trials"]) == {"c0", "fitted_c"}
    assert all(
        t["result"]["history"][-1]["success"] for t in states[0]["selection"]["trials"].values()
    )


def test_changed_protected_owner_forces_original_fallback(monkeypatch):
    evidence = setup(monkeypatch, shared=True)
    original = controller.single_candidate

    def changed(*args):
        candidate = deepcopy(original(*args))
        candidate["arms"]["fitted_c"]["owners"]["old"] = 999
        return candidate

    monkeypatch.setattr(controller, "single_candidate", changed)
    result = controller.recover_tracks(
        {}, evidence, run_stage=execute, discovery_allowed=lambda: True
    )
    assert result["selected"] is None and result["decision"] == "ALGO02_fallback"
    assert "incumbent owner" in result["failure"]


def test_joint_batch_failure_cannot_publish_scientific_fallback(monkeypatch):
    from leo.analysis.localization_v3.joint_recovery import QuadratureExecutionFailure

    evidence = setup(monkeypatch)
    monkeypatch.setattr(controller, 'probe_joint', lambda *a: {})
    monkeypatch.setattr(controller, 'fit_joint', lambda *a, **kw: {})

    def interrupted(*args, **kwargs):
        raise QuadratureExecutionFailure('incomplete audit')

    monkeypatch.setattr(controller, 'audit_joint', interrupted)
    with pytest.raises(QuadratureExecutionFailure, match='incomplete audit'):
        controller.recover_tracks({}, evidence, run_stage=execute, discovery_allowed=lambda: True,
                                  map_joint_batches=object())
