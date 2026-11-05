from copy import deepcopy
from types import SimpleNamespace

import numpy as np
import pytest

from leo.analysis.localization_v3 import annotation_replay as replay
from leo.analysis.localization_v3.recovery_partitions import partition_schedule, planned_split


def fixture():
    times = np.arange(60.0, 140.0)
    base_times = np.arange(0.0, 200.0, 2.0)
    ids = [f"o{i}" for i in range(len(times))]
    track = dict(
        key="track", times=times, values=np.arange(len(times), dtype=float), observation_ids=ids
    )
    target = dict(
        track_id="t",
        track_index=0,
        component="track",
        observation_ids=ids,
        all_track_observation_ids=ids,
    )
    base = SimpleNamespace(flat_times=base_times)
    context = dict(
        scan=SimpleNamespace(tracks=[track], norads=[10, 20]),
        problems={"c0": (base, None)},
        keep=np.ones(len(base_times), bool),
        node={},
    )
    full = np.r_[base_times, times]
    seeds, plan = partition_schedule(full, times)
    folds = []
    for seed in seeds:
        _, _, split = planned_split(full, times, seed, plan)
        proposals = [
            dict(
                candidate_index=j,
                norad=n,
                alias=j - 1,
                arms={
                    a: dict(scores={"conditional_target": dict(negative_twice_log_density=100.0)})
                    for a in replay.ARMS
                },
            )
            for j, n in enumerate((10, 20))
        ]
        folds.append(dict(seed=seed, split=split, proposals=proposals))
    annotation = dict(
        result=dict(
            track_id="t", component="track", folds=folds, phase_outside_reference_window=True
        ),
        protocol=dict(
            target=target, partition_plan=plan, phase_step_s=0.1, uncalibrated_phase_mixture=True
        ),
    )
    return context, dict(tracks=[target]), annotation


def test_replay_preserves_every_proposal_alias_split_and_target_calibration_role(monkeypatch):
    context, inventory, annotation = fixture()
    original = deepcopy(annotation)
    calls, scored = [], []
    monkeypatch.setattr(replay, "check_predictive_role", lambda *a: None)

    def training(d, node, keep, arm, **kw):
        calls.append((arm, keep.copy(), kw))
        p = SimpleNamespace(
            keep=keep,
            labels=[0],
            sky={"time_s": np.array([-100.0, 1000.0])},
            flat_times=d["problems"]["c0"][0].flat_times,
            flat_labels=np.zeros(len(keep), int),
            state=lambda x: dict(phases=np.zeros(1)),
        )
        return p, np.zeros(2), dict(history=[dict(optimizer={"recorded": True})])

    def models(d, p, x, i, j, **kw):
        assert kw == dict(phase_step=0.1, uncalibrated_phase_mixture=True)
        n = len(d["scan"].tracks[i]["times"])
        return (
            np.zeros((3, n)),
            np.eye(n),
            np.zeros(3),
            np.array([-1.0, 0.0, 1.0]),
            np.array([20.0, 30.0, 40.0]),
            {},
        )

    def mixture(observed, mu, cov, lp, train, held):
        scored.append((observed.copy(), train.copy(), held.copy()))
        assert not np.any(train & held)
        return dict(
            negative_twice_log_density=5.0,
            rms_hz=2.0,
            training_mixture_weights=np.array([0.0, 1.0, 0.0]),
        )

    monkeypatch.setattr(replay, "fit_training", training)
    monkeypatch.setattr(replay, "prediction_models", models)
    monkeypatch.setattr(replay, "mixture_prediction", mixture)
    monkeypatch.setattr(replay, "identity_consensus", lambda *a, **kw: dict(status="test"))
    result = replay.replay_annotation(context, inventory, annotation)
    assert replay.competition_signature(result["result"]) == replay.competition_signature(
        original["result"]
    )
    assert annotation == original
    assert len(calls) == 6 and len(scored) == 12
    assert all(kw == dict(reference_limit_s=30.0, record_optimizer=True) for _, _, kw in calls)
    for fold in result["result"]["folds"]:
        for proposal in fold["proposals"]:
            for arm in proposal["arms"].values():
                assert arm["baseline15_score_difference"] == -95.0
                assert arm["target_enters_calibration_equations"] is False
                assert arm["final_training_reference_domain"]["in_domain"]


def test_frozen_target_order_timestamps_and_catalogue_identity_are_protected():
    context, inventory, annotation = fixture()
    context["scan"].tracks[0]["observation_ids"] = list(
        reversed(context["scan"].tracks[0]["observation_ids"])
    )
    with pytest.raises(ValueError, match="chronological"):
        replay.target_context(context, inventory, annotation["result"], annotation["protocol"])
    context, inventory, annotation = fixture()
    context["scan"].tracks[0]["times"] += 0.01
    with pytest.raises(ValueError, match="timestamps"):
        replay.target_context(context, inventory, annotation["result"], annotation["protocol"])


def test_replay_requires_overflow_and_unchanged_physical_budget():
    context, inventory, annotation = fixture()
    annotation["result"].pop("phase_outside_reference_window")
    with pytest.raises(ValueError, match="saved phase overflow"):
        replay.replay_annotation(context, inventory, annotation)
    annotation["result"]["maximum_phase_overflow_s"] = 0.01
    annotation["protocol"]["phase_box_s"] = [-30, 30]
    with pytest.raises(ValueError, match="physical noise or target phase"):
        replay.replay_annotation(context, inventory, annotation)
