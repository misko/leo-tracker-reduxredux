"""Only predictive and numerical checkpoints receive the annotation optimizer port."""

from dataclasses import replace

import pytest

from leo.application import localization_v3 as application
from leo.application import localization_v3_engine as engine
from tests.application.test_localization_v3_engine import fixture


def test_engine_scopes_annotation_optimizer_to_predictive_and_numerical(monkeypatch):
    prepared, region, catalogue, execution, calls, *_ = fixture(monkeypatch)
    fit = object()
    execution = replace(execution, annotation_training_fit=fit)
    engine.infer_prepared(prepared, region, catalogue, identities=["scan"],
                          collect_history=object(), execution=execution)
    for name, _, kwargs in calls:
        if name in ("recover_predictive_checkpoint", "recover_numerical_checkpoint"):
            assert kwargs["annotation_training_fit"] is fit
        else:
            assert "annotation_training_fit" not in kwargs


@pytest.mark.parametrize("injected", [False, True])
@pytest.mark.parametrize("mode", ["predictive", "numerical"])
def test_application_checkpoint_forwards_optional_fit_without_changing_default(
    monkeypatch, injected, mode
):
    fit, seen = object(), []

    def recover(*args, **kwargs):
        seen.append(kwargs)
        return {"selected": None}

    monkeypatch.setattr(application, "recover_tracks" if mode == "predictive" else
                        "replay_recovery", recover)
    prepared = dict(status="track_recovery_prepared", recovery_context={}, inventory={})
    kwargs = dict(run_stage=lambda name, operation: (True, operation()),
                  discovery_allowed=lambda: True, clock=lambda: 0.0)
    if injected:
        kwargs["annotation_training_fit"] = fit
    if mode == "predictive":
        application.recover_predictive_checkpoint(prepared, inventory_seconds=0.0, **kwargs)
    else:
        predictive = dict(status="predictive_recovery_evaluated", recovery={}, completed_stages={})
        application.recover_numerical_checkpoint(
            prepared, predictive, charge_reused=lambda seconds: None, **kwargs)
    assert len(seen) == 1
    assert (seen[0]["annotation_training_fit"] is fit) if injected else (
        "annotation_training_fit" not in seen[0])
