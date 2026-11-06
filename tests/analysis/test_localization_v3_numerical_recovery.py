from copy import deepcopy

import pytest

from leo.analysis.localization_v3 import numerical_recovery as replay


def fixture():
    targets = [
        dict(track_id=f"t{i}", observation_ids=[f"n{i}"], inactive_fragment=False) for i in range(3)
    ]
    owners = {a: dict(owners={"old": 1}) for a in replay.ARMS}
    evidence = dict(
        inventory=dict(summary=[]),
        selected_targets=targets,
        eligible_targets=3,
        publication_support=owners,
    )
    incumbent = dict(
        selected=dict(arms={a: dict(owners={"old": 1, "prior": 2}) for a in replay.ARMS})
    )
    candidate = dict(
        selected=dict(arms={a: dict(owners={"old": 1, "prior": 2, "new": 3}) for a in replay.ARMS})
    )
    saved = {"inventory": dict(seconds=3.0, value=evidence)}
    for i in (0, 2):
        saved[f"target-{i}-annotation"] = dict(
            seconds=10.0, value=dict(protocol={}, result=dict(track_id=f"t{i}", folds=[f"t{i}"]))
        )
        saved[f"target-{i}-inclusion"] = dict(seconds=20.0, value=dict(control={}, label=f"fit{i}"))
        saved[f"target-{i}-audit"] = dict(seconds=5.0, value=dict(label=f"audit{i}"))
    return evidence, incumbent, candidate, saved


def execute(name, operation):
    try:
        return True, operation()
    except ValueError:
        return False, None


@pytest.mark.parametrize('port', ['map_inclusion_arms', 'map_joint_batches'])
def test_numerical_replay_forwards_arm_mapper_to_controller(monkeypatch, port):
    evidence, incumbent, candidate, saved = fixture()
    mapper, seen = object(), []
    monkeypatch.setattr(replay, 'recover_tracks',
                        lambda *a, **k: seen.append(k[port]) or candidate)
    run(evidence, incumbent, saved, **{port: mapper})
    assert seen == [mapper]


def routes(monkeypatch, *, shared=True):
    monkeypatch.setattr(replay, "identity_consensus", lambda *a, **kw: dict(norad=3))
    monkeypatch.setattr(replay, "shared_family_route", lambda *a: shared)


@pytest.mark.parametrize("admitted", [True, False])
def test_only_adopted_numerical_likelihood_replaces_checkpoint(monkeypatch, admitted):
    evidence, incumbent, candidate, saved = fixture()
    if not admitted:
        candidate["selected"]["arms"]["c0"]["owners"].pop("prior")

    def recover(*args, on_selection, **kwargs):
        on_selection({"chosen": "numerical"})
        return candidate

    monkeypatch.setattr(replay, "recover_tracks", recover)
    states = []
    result = run(evidence, incumbent, saved, on_selection=states.append)
    assert states == ([{"chosen": "numerical"}] if admitted else [])
    assert (result["decision"] == "ALGO04_additive") is admitted


def run(evidence, incumbent, saved, **kwargs):
    return replay.replay_recovery(
        {},
        evidence,
        incumbent,
        saved,
        run_stage=kwargs.pop("run_stage", execute),
        discovery_allowed=lambda: True,
        clock=kwargs.pop("clock", lambda: 0.0),
        charge_reused=kwargs.pop("charge_reused", lambda _: None),
        **kwargs,
    )


def test_completed_target_filter_remaps_cache_and_charges_reused_stages(monkeypatch):
    evidence, incumbent, candidate, saved = fixture()
    original = deepcopy(saved)
    charges, admitted = [], []
    routes(monkeypatch)

    def recover(context, narrowed, *, run_stage, discovery_allowed):
        assert [t["track_id"] for t in narrowed["selected_targets"]] == ["t0", "t2"]
        assert narrowed["eligible_targets"] == 3
        for i, old in enumerate((0, 2)):
            for kind in ("annotation", "inclusion", "audit"):

                def forbidden():
                    raise AssertionError("unchanged scientific stage must be reused")

                ok, value = run_stage(f"target-{i}-{kind}", forbidden)
                assert ok and value == original[f"target-{old}-{kind}"]["value"]
                assert value is not saved[f"target-{old}-{kind}"]["value"]
        return candidate

    def execute_recorded(name, operation):
        admitted.append(name)
        return execute(name, operation)

    monkeypatch.setattr(replay, "recover_tracks", recover)
    result = run(
        evidence, incumbent, saved, run_stage=execute_recorded, charge_reused=charges.append
    )
    assert result["decision"] == "ALGO04_additive"
    assert len(admitted) == 7 and charges == [3.0] + [10.0, 20.0, 5.0] * 2
    assert result["completed_target_ids"] == ["t0", "t2"]
    assert saved == original


def test_replay_keeps_original_competition_and_recomputes_dependent_shared_fit(monkeypatch):
    evidence, incumbent, candidate, saved = fixture()
    saved["target-0-annotation"]["value"]["result"]["phase_outside_reference_window"] = True
    routes(monkeypatch)
    calls = []

    def annotation(context, inv, frozen):
        calls.append("replay")
        return dict(frozen, protocol=dict(numerical_replay={"frozen_competition": True}))

    monkeypatch.setattr(replay, "replay_annotation", annotation)

    def recover(context, narrowed, *, run_stage, discovery_allowed):
        ok, value = run_stage("target-0-annotation", lambda: calls.append("renomination"))
        assert ok and value["protocol"]["numerical_replay"]
        policies = []
        for name in ("inclusion", "audit"):

            def operation(name=name):
                policies.append(context["numerical_policy"])
                calls.append(name)
                return {"fresh": name}

            assert run_stage("target-0-" + name, operation)[0]
        assert policies[0] is not policies[1]
        return candidate

    monkeypatch.setattr(replay, "recover_tracks", recover)
    result = run(evidence, incumbent, saved)
    assert calls == ["replay", "inclusion", "audit"]
    assert not any(r["reused"] for r in result["stage_replay"] if r["name"] != "inventory")


def test_new_family_recomputed_and_missing_shared_audit_never_inferred(monkeypatch):
    evidence, incumbent, candidate, saved = fixture()
    routes(monkeypatch, shared=False)

    def recover(context, narrowed, *, run_stage, discovery_allowed):
        run_stage("target-0-annotation", lambda: None)
        ok, value = run_stage("target-0-inclusion", lambda: {"new": True})
        assert ok and value == {"new": True}
        return candidate

    monkeypatch.setattr(replay, "recover_tracks", recover)
    assert run(evidence, incumbent, saved)["stage_replay"][2]["reused"] is False
    routes(monkeypatch, shared=True)
    saved.pop("target-0-audit")

    def missing(context, narrowed, *, run_stage, discovery_allowed):
        run_stage("target-0-annotation", lambda: None)
        run_stage("target-0-inclusion", lambda: None)
        assert run_stage("target-0-audit", lambda: {"inferred": True}) == (False, None)
        return dict(selected=None)

    monkeypatch.setattr(replay, "recover_tracks", missing)
    result = run(evidence, incumbent, saved)
    assert result["decision"] == "ALGO03_fallback" and result["retained"] == incumbent


def test_reuse_remains_subject_to_stage_budget_and_deducts_copy_time(monkeypatch):
    evidence, incumbent, candidate, saved = fixture()
    clock = iter([0.0, 0.0, 3.0, 5.0])
    charges = []

    def recover(context, narrowed, *, run_stage, discovery_allowed):
        assert run_stage("target-0-annotation", lambda: None)[0]
        assert run_stage("target-1-annotation", lambda: None) == (False, None)
        return candidate

    def budget(name, operation):
        return (
            execute(name, operation)
            if name in ("inventory", "target-0-annotation")
            else (False, None)
        )

    monkeypatch.setattr(replay, "recover_tracks", recover)
    run(
        evidence,
        incumbent,
        saved,
        run_stage=budget,
        clock=lambda: next(clock),
        charge_reused=charges.append,
    )
    assert charges == [3.0, 8.0]


@pytest.mark.parametrize("arm", replay.ARMS)
@pytest.mark.parametrize("replacement", [None, 999])
def test_additive_gate_rejects_loss_or_reassignment_in_either_arm(arm, replacement):
    _, incumbent, candidate, _ = fixture()
    if replacement is None:
        candidate["selected"]["arms"][arm]["owners"].pop("prior")
    else:
        candidate["selected"]["arms"][arm]["owners"]["prior"] = replacement
    assert replay.additive_admission(incumbent, candidate) == (
        False,
        "would_lose_or_change_published_ALGO03_owner",
    )


def test_cache_validation_and_controller_overflow_trigger():
    evidence, incumbent, _, saved = fixture()
    saved["target-0-annotation"]["seconds"] = float("nan")
    with pytest.raises(ValueError, match="duration"):
        run(evidence, incumbent, saved)
    assert replay.overflow({"history": [{"phase_outside_reference_window": True}]})
    assert not replay.overflow({"maximum_phase_overflow_s": 1.0})
