"""Annotation optimizer selection uses owned contexts and unchanged training recipes."""

from copy import deepcopy
from types import SimpleNamespace

import numpy as np
import pytest
from check_algo07v3_scan_likelihood import fingerprint

from leo.analysis.localization_v3 import (
    annotation_replay,
    numerical_recovery,
    prediction,
    recovery_controller,
)
from leo.analysis.localization_v3 import predictive_annotation as annotation
from leo.analysis.localization_v3.numerical_policy import NumericalPolicy
from tests.analysis.test_localization_v3_annotation_replay import fixture as replay_fixture
from tests.analysis.test_localization_v3_numerical_recovery import fixture as recovery_fixture
from tests.analysis.test_localization_v3_predictive_annotation import fixture as annotation_fixture


class TrainingFit:
    def __init__(self):
        self.policy = {"name": "tiny-test-optimizer", "objective_cap": 9}
        self.calls = []

    def __call__(self, problem, start, *, iterations):
        self.calls.append((problem.arm, iterations, problem.keep.copy()))
        return dict(
            parameters=np.asarray(start) + 0.05,
            evaluations=9,
            converged=False,
            budget_exhausted=True,
            stopped="objective cap",
            scipy_result={"success": False, "status": 1},
            solution_origin="best evaluated",
            history_kind="physical objective evaluations",
            stationarity={"satisfied": False},
            optimizer_policy=deepcopy(self.policy),
            history=[{"value": i} for i in range(9)],
        )


def fake_training(monkeypatch):
    monkeypatch.setattr(prediction, "prior_means", lambda *a: (np.zeros(1), []))
    monkeypatch.setattr(prediction, "cached", lambda p: p)

    def problem(scan, node, keep, arm, reference, powers, means, model, events, **kwargs):
        return SimpleNamespace(
            arm=arm, keep=np.asarray(keep).copy(), reference=np.asarray(reference).copy(),
            labels=[0], flat_labels=np.zeros(len(keep), int),
            flat_times=np.arange(len(keep), dtype=float),
            sky={"time_s": np.array([-1000.0, 1000.0])},
            state=lambda x: {"phases": np.zeros(1)},
            calculate=lambda x: {"negative_twice_elbo": float(np.asarray(x).sum())},
        )

    monkeypatch.setattr(prediction, "make_event_problem", problem)
    monkeypatch.setattr(
        prediction, "fit", lambda p, start, **kw: {"parameters": np.asarray(start) + 0.01}
    )


def training_context():
    return dict(scan=None, node={}, powers=np.ones(1), model={}, entries=[],
                keep=np.ones(5, bool))


@pytest.mark.parametrize("mapped", [False, True])
def test_injected_optimizer_trains_both_arms_and_preserves_recipes(monkeypatch, mapped):
    d, inventory, seeds = annotation_fixture(monkeypatch, annotation)
    d.update(powers=np.ones(1), model={}, entries=[])
    fake_training(monkeypatch)
    monkeypatch.setattr(annotation, "fit_training", prediction.fit_training)
    fit = TrainingFit()
    before = dict(d)
    result = annotation.annotate(
        d, inventory, "target", training_fit=fit,
        **({"map_training": lambda operation, tasks: list(map(operation, tasks))}
           if mapped else {}),
    )
    assert d == before and "annotation_training_fit" not in d
    assert [arm for arm, _, _ in fit.calls] == [
        arm for _ in seeds for arm in annotation.ARMS for _ in range(5)
    ]
    assert all(iterations == 48 for _, iterations, _ in fit.calls)
    assert result["protocol"]["training_optimizer_policy"] == fit.policy
    for fold in result["result"]["folds"]:
        for proposal in fold["proposals"]:
            for meta in proposal["arms"].values():
                np.testing.assert_allclose(meta["endpoint_east_north_km"], [0.25, 0.25])
                assert len(meta["history"]) == 5
                assert meta["training_optimizer_policy"] == fit.policy
                for row in meta["history"]:
                    assert row["optimizer"]["evaluations"] == 9
                    assert row["optimizer"]["budget_exhausted"]
                    assert row["optimizer"]["stationarity"] == {"satisfied": False}
                    assert not row["optimizer"]["history_stored"]
                    assert "history" not in row["optimizer"]
    fit.policy["objective_cap"] = 1
    assert result["protocol"]["training_optimizer_policy"]["objective_cap"] == 9


@pytest.mark.parametrize("arm", prediction.ARMS)
def test_injected_recipe_reconstruction_keeps_exact_objective(monkeypatch, arm):
    fake_training(monkeypatch)
    fit = TrainingFit()
    d = dict(training_context(), annotation_training_fit=fit)
    p, x, meta = prediction.fit_training(d, d["node"], d["keep"], arm)
    record = prediction.training_record(d, d["keep"], arm)
    restored, restored_x, restored_meta = prediction.restore_training(d, d["keep"], arm, record)
    assert fingerprint((x, meta, p.calculate(x))) == fingerprint(
        (restored_x, restored_meta, restored.calculate(restored_x)))
    record["metadata"]["training_objective"] += 1
    with pytest.raises(ValueError, match="likelihood differs"):
        prediction.restore_training(d, d["keep"], arm, record)


def test_default_training_metadata_and_full_record_branch_are_unchanged(monkeypatch):
    fake_training(monkeypatch)
    d = training_context()
    _, x, meta = prediction.fit_training(d, d["node"], d["keep"], "c0")
    np.testing.assert_allclose(x, [0.05, 0.05])
    assert "training_optimizer_policy" not in meta
    assert all("optimizer" not in row for row in meta["history"])
    fit = TrainingFit()
    _, _, injected = prediction.fit_training(
        dict(d, annotation_training_fit=fit), d["node"], d["keep"], "c0", record_optimizer=True)
    assert all(len(row["optimizer"]["history"]) == 9 for row in injected["history"])


@pytest.mark.parametrize("stateful", ["callback", "numerical_policy"])
def test_injected_stateful_annotation_stays_serial(monkeypatch, stateful):
    d, inventory, seeds = annotation_fixture(monkeypatch, annotation)
    d.update(powers=np.ones(1), model={}, entries=[])
    fake_training(monkeypatch)
    monkeypatch.setattr(annotation, "fit_training", prediction.fit_training)
    if stateful == "numerical_policy":
        d["numerical_policy"] = NumericalPolicy()
    seen = []

    def forbidden(*args):
        raise AssertionError("Stateful annotation must stay serial")

    annotation.annotate(
        d, inventory, "target", training_fit=TrainingFit(),
        on_proposal=(lambda seed, proposal: seen.append(seed)) if stateful == "callback" else None,
        map_training=forbidden, map_folds=forbidden,
    )
    if stateful == "callback":
        assert seen == [seed for seed in seeds for _ in range(2)]
    else:
        assert d["numerical_policy"].receipt["problem_count"] == 30
        assert len(d["numerical_policy"].receipt["reference_updates"]) == 30
    assert "annotation_training_fit" not in d


def test_replay_copies_context_and_keeps_injected_policy_with_numerical_receipts(monkeypatch):
    d, inventory, frozen = replay_fixture()
    fake_training(monkeypatch)
    d.update(powers=np.ones(1), model={}, entries=[], numerical_policy=NumericalPolicy())
    fit = TrainingFit()
    frozen["protocol"]["training_optimizer_policy"] = deepcopy(fit.policy)
    monkeypatch.setattr(annotation_replay, "check_predictive_role", lambda *a: None)
    monkeypatch.setattr(annotation_replay, "prediction_models", lambda d, p, x, i, j, **kw: (
        np.zeros((1, 80)), np.eye(80), np.zeros(1), np.zeros(1), np.array([30.0]), {}))
    monkeypatch.setattr(annotation_replay, "mixture_prediction", lambda *a: dict(
        training_mixture_weights=np.ones(1), negative_twice_log_density=5.0, rms_hz=1.0))
    monkeypatch.setattr(annotation_replay, "identity_consensus", lambda *a, **kw: {})
    result = annotation_replay.replay_annotation(d, inventory, frozen, training_fit=fit)
    assert len(fit.calls) == 30
    assert result["protocol"]["training_optimizer_policy"] == fit.policy
    assert len(d["numerical_policy"].receipt["reference_updates"]) == 30
    assert "annotation_training_fit" not in d


@pytest.mark.parametrize("saved,supplied", [(True, False), (False, True), (True, True)])
def test_replay_rejects_missing_or_changed_optimizer_policy(saved, supplied):
    d, inventory, frozen = replay_fixture()
    fit = TrainingFit()
    if saved:
        frozen["protocol"]["training_optimizer_policy"] = {"name": "other"}
    with pytest.raises(ValueError, match="optimizer policy"):
        annotation_replay.replay_annotation(
            d, inventory, frozen, **({"training_fit": fit} if supplied else {}))


def test_numerical_recovery_forwards_fit_to_replaced_replay_operation(monkeypatch):
    evidence, incumbent, candidate, saved = recovery_fixture()
    saved["target-0-annotation"]["value"]["result"]["phase_outside_reference_window"] = True
    fit, seen = TrainingFit(), []
    for record in saved.values():
        if "protocol" in record["value"]:
            record["value"]["protocol"]["training_optimizer_policy"] = deepcopy(fit.policy)

    def replay(context, inventory, frozen, *, training_fit):
        assert training_fit is fit and "annotation_training_fit" not in context
        seen.append(frozen["result"]["track_id"])
        return frozen

    def recover(context, narrowed, *, run_stage, annotation_training_fit, **kwargs):
        assert annotation_training_fit is fit
        assert "annotation_training_fit" not in context
        assert run_stage("target-0-annotation", lambda: pytest.fail("renomination"))[0]
        return candidate

    monkeypatch.setattr(numerical_recovery, "replay_annotation", replay)
    monkeypatch.setattr(numerical_recovery, "recover_tracks", recover)
    numerical_recovery.replay_recovery(
        {}, evidence, incumbent, saved, run_stage=lambda name, operation: (True, operation()),
        discovery_allowed=lambda: True, clock=lambda: 0.0, charge_reused=lambda seconds: None,
        annotation_training_fit=fit)
    assert seen == ["t0"]


@pytest.mark.parametrize("injected", [False, True])
def test_numerical_recovery_rejects_reused_optimizer_mismatch_before_execution(injected):
    evidence, incumbent, _, saved = recovery_fixture()
    saved["target-0-annotation"]["value"]["protocol"]["training_optimizer_policy"] = {
        "name": "other"
    }

    def forbidden(*args):
        raise AssertionError("Policy mismatch must reject before any stage executes")

    with pytest.raises(ValueError, match="optimizer policy"):
        numerical_recovery.replay_recovery(
            {}, evidence, incumbent, saved, run_stage=forbidden,
            discovery_allowed=forbidden, clock=forbidden, charge_reused=forbidden,
            **({"annotation_training_fit": TrainingFit()} if injected else {}),
        )


def test_controller_injection_never_enters_inclusion_context(monkeypatch):
    context, fit, observed = {}, TrainingFit(), []
    evidence = dict(
        inventory=dict(summary=[]), publication_support={}, eligible_targets=1,
        selected_targets=[dict(track_id="t", observation_ids=["o"], inactive_fragment=False)])

    def annotate(context_seen, inventory, track, *, training_fit, **kwargs):
        assert context_seen is context and training_fit is fit
        return dict(result=dict(folds=[]), protocol={})

    def include(context_seen, *args, **kwargs):
        observed.append(context_seen)
        assert context_seen is context and "annotation_training_fit" not in context_seen
        return {}

    monkeypatch.setattr(recovery_controller, "annotate", annotate)
    monkeypatch.setattr(recovery_controller, "identity_consensus", lambda *a, **kw: dict(
        status="conditionally_supported_identity", norad=1))
    monkeypatch.setattr(recovery_controller, "require_distinct_annotation", lambda *a: None)
    monkeypatch.setattr(recovery_controller, "shared_family_route", lambda *a: True)
    monkeypatch.setattr(recovery_controller, "fit_shared", include)
    monkeypatch.setattr(recovery_controller, "audit_inclusion", lambda *a, **kw: {})
    monkeypatch.setattr(recovery_controller, "single_candidate", lambda *a: None)
    recovery_controller.recover_tracks(
        context, evidence, run_stage=lambda name, operation: (True, operation()),
        discovery_allowed=lambda: True, annotation_training_fit=fit)
    assert observed == [context] and context == {}
