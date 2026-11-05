from copy import deepcopy
from types import SimpleNamespace

import numpy as np
import pytest

from leo.analysis.localization_v3.gap_fragments import (
    PERIOD,
    gap_context,
    partitions,
    prepare_gap,
    source_digest,
)


def fixture():
    times = np.r_[np.arange(12.0), np.arange(20.0, 32.0)]
    ids = [f"point-{i}" for i in range(len(times))]
    measured = times**2
    parent = dict(
        key="parent",
        source_id="SCAN",
        times=times,
        values=measured + PERIOD,
        observation_ids=ids,
        receiver=1,
        channel=8,
        rf_hz=12e9,
        pieces=[],
        residual_rms_hz=2.0,
    )
    scan = SimpleNamespace(
        case="SCAN", tracks=[parent], white=[object()], rx_basis=[object()], calibration=object()
    )
    observations = [
        dict(
            observation_id=o, time_s=t, measured_cfo_hz=y, receiver=1, channel=8, actual_rf_hz=12e9
        )
        for o, t, y in zip(ids, times, measured, strict=True)
    ]
    inventory = dict(
        tracks=[dict(track_id="parent-id", track_index=0)],
        policy={
            "c0": dict(proposed_associated_ids=[]),
            "fitted_c": dict(proposed_associated_ids=[]),
        },
    )
    context = dict(scan=scan, problems={}, entries=[])
    source = prepare_gap(context, inventory, observations, "parent-id")
    return context, inventory, observations, source


def test_gap_boundaries_are_timing_only_and_complete_components():
    assert partitions(np.r_[np.arange(12.0), np.arange(16.0, 28.0)]) == [(0, 24)]
    assert partitions(np.r_[np.arange(12.0), np.arange(16.0001, 28.0001)]) == [(0, 12), (12, 24)]
    assert partitions(np.linspace(0, 10, 12)) == [(0, 12)]
    assert partitions(np.linspace(0, 9.999, 12)) == []
    assert partitions(np.linspace(0, 10, 11)) == []


@pytest.mark.parametrize("times", [[], [1, 1], [2, 1], [0, np.nan], [[0, 1]]])
def test_invalid_times_are_rejected(times):
    with pytest.raises(ValueError, match="strictly increasing"):
        partitions(times)


def test_gap_append_preserves_graph_calibration_and_measurements():
    context, inventory, observations, source = fixture()
    branch = source["branches"][0]
    changed, target = gap_context(context, inventory, source, branch["branch_id"], observations)
    old, new = context["scan"], changed["scan"]
    assert len(old.tracks) == 1 and len(new.tracks) == 2
    assert new.tracks[0] is old.tracks[0]
    assert new.white[0] is old.white[0] and new.rx_basis[0] is old.rx_basis[0]
    assert new.calibration is old.calibration
    np.testing.assert_array_equal(new.tracks[1]["values"], old.tracks[0]["values"][:12])
    assert new.tracks[1]["bank"] == "CH5-8"
    assert target["gap_source_sha256"] == source_digest(source)
    assert target["observation_ids"] == old.tracks[0]["observation_ids"][:12]
    assert source["protocol"]["retained_points"] == 24


@pytest.mark.parametrize("owner", ["c0", "fitted_c", "curved", "predictive"])
def test_gap_cannot_reuse_any_baseline_owned_point(owner):
    context, inventory, observations, source = fixture()
    point = observations[0]["observation_id"]
    if owner in inventory["policy"]:
        inventory["policy"][owner]["proposed_associated_ids"] = [point]
    elif owner == "curved":
        problem = SimpleNamespace(
            members=[0], slices=[slice(0, 24)], keep=np.r_[True, np.zeros(23, bool)]
        )
        context["problems"]["c0"] = problem, None
    else:
        context["entries"] = [dict(observation_ids=[point])]
    with pytest.raises(ValueError, match="overlaps"):
        gap_context(context, inventory, source, source["branches"][0]["branch_id"], observations)


@pytest.mark.parametrize(
    "corruption, message",
    [
        ("frequency", "measured CFO"),
        ("time", "timestamps"),
        ("lane", "lanes"),
        ("partial", "whole time-gap"),
        ("policy", "gap policy"),
        ("parent", "parent changed"),
    ],
)
def test_gap_rejects_corrupted_evidence(corruption, message):
    context, inventory, observations, source = fixture()
    source = deepcopy(source)
    branch = source["branches"][0]
    if corruption == "frequency":
        branch["values_hz"][0] += 1
    elif corruption == "time":
        branch["times_s"][0] += 0.1
    elif corruption == "lane":
        observations[0]["actual_rf_hz"] += 1
    elif corruption == "partial":
        branch["observation_ids"] = branch["observation_ids"][:-1]
    elif corruption == "policy":
        source["protocol"]["gap_s"] = 6
    else:
        source["protocol"]["parent_observation_ids"] = []
    with pytest.raises(ValueError, match=message):
        gap_context(context, inventory, source, branch["branch_id"], observations)
