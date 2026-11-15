from copy import deepcopy
from types import SimpleNamespace

import numpy as np
import pytest

from leo.analysis.localization_v3 import omitted_track_proposals as proposals
from leo.analysis.research.retained_track_likelihood import PERIOD


def fixture(monkeypatch, count=4):
    times = np.linspace(20.0, 50.0, 25)
    tracks = [dict(key=f"track-{i}", times=times.copy(), values=1000 * times,
                   observation_ids=[f"{i}-{k}" for k in range(len(times))],
                   rf_hz=11.5e9, receiver=1, channel=1, arm_noise=0.0)
              for i in range(count)]
    scan = SimpleNamespace(
        tracks=tracks, curved=[], norads=np.array([100, 200]),
        sky=dict(time_s=np.array([0.0, 50.0, 100.0]),
                 position_km=np.ones((2, 3, 3)), velocity_km_s=np.ones((2, 3, 3))),
        rx_basis=[np.zeros((25, 1)) for _ in tracks],
        hardware=lambda t, beta: beta[0] * t["arm_noise"] * np.sin(t["times"]),
        search_region=SimpleNamespace(latlon=lambda xy: tuple(xy)))
    problems = {
        arm: (SimpleNamespace(members=[], keep=np.zeros(0, bool), slices=[],
                              state=lambda x: dict(beta=np.array([x[0]]),
                                                   smooth=np.zeros((2, 1)))), np.array([k, 0.0]))
        for k, arm in enumerate(proposals.ARMS)
    }
    context = dict(scan=scan, problems=problems)
    rows = [dict(arm=arm, track_id=f"target-{i}", track_index=i, component=t["key"],
                 observation_ids=t["observation_ids"].copy(),
                 all_track_observation_ids=t["observation_ids"].copy(), current_large=True,
                 current=dict(wholly_unassociated=True))
            for arm in proposals.ARMS for i, t in enumerate(tracks)]
    evidence = dict(inventory=dict(tracks=rows), owners={a: {} for a in proposals.ARMS},
                    selected_targets=[], target_limit=0,
                    policy_omitted_track_ids=[f"target-{i}" for i in range(count)])
    calls = []

    def grids(bank, query, positions, *, phase_seconds):
        calls.append(dict(times=query.copy(), positions=positions, phase=phase_seconds))
        f = np.array([1000 * query, -1000 * query])
        return [(f.copy(), np.ones_like(f)) for _ in positions]

    monkeypatch.setattr(proposals, "phase_frequency_grids", grids)
    return context, evidence, calls


def test_outside_old_prefix_is_ranked_once_for_both_arms_without_mutating_inputs(monkeypatch):
    context, evidence, calls = fixture(monkeypatch, 10)
    context["scan"].curved = list(range(9))
    context["scan"].tracks[9]["values"] += PERIOD
    before = deepcopy(evidence)
    track_values = context["scan"].tracks[9]["values"].copy()
    result = proposals.rank_omitted_tracks(context, evidence)
    assert result["policy"] == proposals.POLICY
    assert [r["track_id"] for r in result["targets"]] == ["target-9"]
    target = result["targets"][0]
    assert target == dict(before["inventory"]["tracks"][9], inactive_fragment=False)
    assert not any(k.startswith("nomination") for k in target)
    assert result["rows"][0]["nomination_norad"] == 100
    assert result["rows"][0]["nomination_alias"] == -1
    assert len(calls) == len(proposals.PHASES)
    assert {len(c["times"]) for c in calls} == {16}
    assert all(len(c["positions"]) == 2 for c in calls)
    assert result["protocol"]["independent_annotation_inclusion_and_audit_required"]
    assert not result["protocol"]["position_inclusion_authorized"]
    assert not result["protocol"]["target_label_or_alias_supplied_to_annotation"]
    assert not result["protocol"]["GPS_used"]
    assert evidence == before
    np.testing.assert_array_equal(context["scan"].tracks[9]["values"], track_values)


def test_only_large_wholly_unowned_original_uncurved_tracks_are_eligible(monkeypatch):
    context, evidence, _ = fixture(monkeypatch)
    context["scan"].curved = [0]
    evidence["owners"]["fitted_c"]["1-0"] = 300
    evidence["inventory"]["tracks"][2]["observation_ids"] = ["2-0"]
    evidence["inventory"]["tracks"][3]["current_large"] = False
    result = proposals.rank_omitted_tracks(context, evidence)
    assert result["eligible_targets"] == 0 and result["targets"] == []
    assert len(result["excluded"]) == 3


def test_ranking_uses_worse_arm_and_cap_has_deterministic_ties(monkeypatch):
    context, evidence, _ = fixture(monkeypatch)
    for i, track in enumerate(context["scan"].tracks):
        track["values"] += (0 if i == 0 else 30) * np.sin(track["times"])
    context["scan"].tracks[0]["arm_noise"] = 200.0
    result = proposals.rank_omitted_tracks(context, evidence)
    assert [r["track_id"] for r in result["targets"]] == ["target-1", "target-2"]
    rows = {r["track_id"]: r for r in result["rows"]}
    assert rows["target-0"]["arms"]["c0"]["cost"] < rows["target-1"]["arms"]["c0"]["cost"]
    assert rows["target-0"]["rank"] == 4
    evidence["inventory"]["tracks"].reverse()
    reverse = proposals.rank_omitted_tracks(context, evidence, max_proposals=1)
    assert [r["track_id"] for r in reverse["targets"]] == ["target-1"]


def test_disagreeing_alias_or_invisible_candidates_do_not_nominate(monkeypatch):
    context, evidence, _ = fixture(monkeypatch, 1)
    context["scan"].hardware = lambda t, beta: beta[0] * PERIOD
    result = proposals.rank_omitted_tracks(context, evidence)
    assert result["targets"] == []
    assert result["rows"][0]["status"] == "no_common_plausible_candidate"
    context["scan"].hardware = lambda t, beta: 0.0

    def invisible(bank, query, positions, *, phase_seconds):
        f = np.array([1000 * query, -1000 * query])
        return [(f, -np.ones_like(f)) for _ in positions]

    monkeypatch.setattr(proposals, "phase_frequency_grids", invisible)
    assert proposals.rank_omitted_tracks(context, evidence)["targets"] == []


def test_second_best_phase_can_supply_the_common_alias(monkeypatch):
    context, evidence, _ = fixture(monkeypatch, 1)

    def grids(bank, query, positions, *, phase_seconds):
        rows = []
        for arm in range(2):
            if arm == 0:
                shift = 0.0 if phase_seconds == -15.0 else PERIOD + 2.0
            else:
                shift = PERIOD + 1.0 if phase_seconds == -15.0 else 2 * PERIOD + 2.0
            f = np.array([1000 * query + shift, -1000 * query])
            rows.append((f, np.ones_like(f)))
        return rows

    monkeypatch.setattr(proposals, "phase_frequency_grids", grids)
    result = proposals.rank_omitted_tracks(context, evidence)
    assert len(result["targets"]) == 1
    row = result["rows"][0]
    assert row["nomination_alias"] == 1
    assert row["arms"]["c0"]["phase_s"] == -12.0
    assert row["arms"]["fitted_c"]["phase_s"] == -15.0


def test_shifted_candidate_is_ranked_without_a_zero_centered_phase_penalty(monkeypatch):
    context, evidence, _ = fixture(monkeypatch, 1)

    def grids(bank, query, positions, *, phase_seconds):
        f = np.array([1000 * query + (phase_seconds - 12) * 10, -1000 * query])
        return [(f, np.ones_like(f)) for _ in positions]

    monkeypatch.setattr(proposals, "phase_frequency_grids", grids)
    result = proposals.rank_omitted_tracks(context, evidence)
    assert result["protocol"]["phase_grid_penalty"] is False
    assert {a["phase_s"] for a in result["rows"][0]["arms"].values()} == {12.0}


@pytest.mark.parametrize("cap", [0, 3, True, 2.0, "2"])
def test_invalid_cap_fails_before_context_or_geometry(cap):
    with pytest.raises(ValueError, match="cap must be one or two"):
        proposals.rank_omitted_tracks(None, None, max_proposals=cap)


def test_whole_native_domain_is_checked_before_uniform_thinning(monkeypatch):
    context, evidence, calls = fixture(monkeypatch, 1)
    context["scan"].tracks[0]["times"][1] = 1.0
    context["scan"].tracks[0]["times"].sort()
    with pytest.raises(ValueError, match="Full omitted track phase domain"):
        proposals.rank_omitted_tracks(context, evidence)
    assert calls == []


def test_active_calibration_membership_and_changed_inventory_fail_closed(monkeypatch):
    context, evidence, calls = fixture(monkeypatch, 1)
    p, _ = context["problems"]["c0"]
    p.members, p.keep, p.slices = [0], np.ones(25, bool), [slice(0, 25)]
    with pytest.raises(ValueError, match="already calibrates"):
        proposals.rank_omitted_tracks(context, evidence)
    assert calls == []
    p.members = []
    evidence["inventory"]["tracks"][1]["component"] = "another-track"
    with pytest.raises(ValueError, match="component differs"):
        proposals.rank_omitted_tracks(context, evidence)
