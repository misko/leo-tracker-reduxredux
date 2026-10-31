"""Synthetic ownership accounting; no orbit, localization or new fit."""

import copy

import pytest

from audit_inventory_publication import audit_case, residual_support


def fixture():
    ids = [f"native-{i}" for i in range(24)]
    track = dict(key="RX2-CH8-T001", receiver=1, channel=7, rf_hz=12e9,
                 observation_ids=ids, times=list(range(24)), values=[0] * 24,
                 quality_status="no_structure_detected")
    observations = [dict(observation_id=oid) for oid in ids]
    gates = [dict(observation_ids=ids[:3], norad=12345)]
    baseline = dict(state="complete", model_version="algo02-causal-family-v1",
                    arms={arm: dict(gates=dict(tracks=gates), linear_gates=[])
                          for arm in ("c0", "fitted_c")})
    inventory = dict(tracks=[], policy={arm: dict(proposed_associated_ids=ids)
                                       for arm in ("c0", "fitted_c")})
    support = dict(all_verified=True, arms={arm: dict(owners={oid: 12345 for oid in ids[:3]},
        unreported_postfit_ids=ids[3:]) for arm in ("c0", "fitted_c")})
    return [track], observations, inventory, support, baseline


def test_omitted_replay_only_source_is_not_published_association():
    tracks, observations, inv, support, baseline = fixture()
    result = audit_case(tracks, observations, inv, support, baseline, baseline)
    arm = result["fitted_c"]
    assert arm["published_ALGO02_associated"] == 3
    assert arm["replay_inventory_proposed_associated"] == 24
    assert arm["unreported_postfit_points"] == 21
    assert arm["unreported_still_unassociated_ALGO04"] == 21
    assert arm["long_native_curves_absent_from_inventory"] == 1
    assert arm["long_native_curves"][0]["published_ALGO02_residual"]["span_s"] == 20


def test_chosen_proof_and_arms_control_actual_unassociated_count():
    tracks, observations, inv, support, baseline = fixture()
    incumbent = dict(state="complete", model_version="algo03-causal-predictive-v1",
                     decision="ALGO02_fallback", selected=None, baseline=baseline)
    selected = {arm: dict(owners={f"native-{i}": 12345 for i in range(n)},
                         associated_ids=[f"native-{i}" for i in range(n)])
                for arm, n in [("c0", 4), ("fitted_c", 6)]}
    candidate = dict(incumbent, selected=dict(arms=selected))
    chosen = dict(state="complete", model_version="algo04-causal-numerical-v1",
                  decision="ALGO03_fallback", incumbent=incumbent, candidate=candidate)
    fallback = audit_case(tracks, observations, inv, support, baseline, chosen)
    assert fallback["fitted_c"]["unreported_still_unassociated_ALGO04"] == 21
    chosen["decision"] = "ALGO04_additive"
    actual = audit_case(tracks, observations, inv, support, baseline, chosen)
    assert actual["c0"]["unreported_still_unassociated_ALGO04"] == 20
    assert actual["fitted_c"]["unreported_still_unassociated_ALGO04"] == 18
    assert actual["fitted_c"]["unreported_associated_ALGO04"] == 3
    assert actual["fitted_c"]["long_native_curves_still_large_unassociated_ALGO04"] == 0


def test_unavailable_chosen_proof_keeps_unknown_count():
    result = audit_case(*fixture())
    assert result["c0"]["unreported_still_unassociated_ALGO04"] is None
    assert result["c0"]["long_native_curves_still_large_unassociated_ALGO04"] is None


def test_partial_replay_mask_can_suppress_large_threshold_without_omitting_row():
    inputs = copy.deepcopy(fixture())
    ids = inputs[0][0]["observation_ids"]
    for arm in ("c0", "fitted_c"):
        inputs[2]["policy"][arm]["proposed_associated_ids"] = ids[:5]
        inputs[2]["tracks"].append(dict(arm=arm, track_index=0, observation_ids=ids[5:]))
        inputs[3]["arms"][arm]["unreported_postfit_ids"] = ids[3:5]
    result = audit_case(*inputs)["c0"]
    assert result["unreported_postfit_points"] == 2
    assert result["long_native_curves_absent_from_inventory"] == 0
    assert result["long_native_curves_suppressed_below_large_threshold"] == 1


def test_mismatched_replay_partition_rejected():
    inputs = copy.deepcopy(fixture())
    inputs[3]["arms"]["c0"]["unreported_postfit_ids"].pop()
    with pytest.raises(ValueError, match="partition"):
        audit_case(*inputs)


def test_whole_source_gap_is_reported_not_hidden():
    track = fixture()[0][0]
    track["times"] = list(range(12)) + list(range(100, 112))
    result = residual_support(track, set())
    assert result["large"] is True
    assert result["maximum_gap_s"] == 89
    assert result["span_s"] == 111
