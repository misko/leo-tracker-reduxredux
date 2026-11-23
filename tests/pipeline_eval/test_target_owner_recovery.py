from copy import deepcopy

import pytest

from leo.contracts.digests import canonical_digest
from reports.ALGO08.v3.target_owner_recovery import concentration, analysis_digest, observation_id, price, reopen
from stereo_lane_schedule import StereoSchedule, recipe


def complete_inputs():
    detector = "sha256:" + "1"*64
    source = dict(raw_recording_authority_digest="sha256:"+"2"*64, qualified=True, sample_rate_hz=10_000_000, session_id="session")
    rows = [dict(visit_index=j, receiver_id=r, channel=1, edge="lower", actual_rf_hz=11e9, valid_start_counter=20*j,
                 payload_start_sample=20*j, candidates=[dict(passed_fractional_margin_gate=True, candidate_rank=0)])
            for j in range(24) for r in range(2)]
    first = dict(source=dict(source, probes=rows, analysis_manifest_sha256=analysis_digest(source, detector, rows)),
                 provenance=dict(window_count=24, processed_windows=24, excluded_windows=[], detector_sha256=detector),
                 delivery_clocks=list(range(24)))
    schedule = StereoSchedule("target")
    omitted = []
    for j in range(24):
        _, slot = schedule.next(("lower", 1, 11e9))
        if slot is not None:
            omitted.append([j, slot])
    new_recipe = recipe("target", detector)
    new_detector = canonical_digest(new_recipe)
    selected = [dict(row, candidates=[]) if [row["visit_index"],row["receiver_id"]] in omitted else row for row in rows]
    masked = dict(first, source=dict(source, probes=selected, analysis_manifest_sha256=analysis_digest(source, new_detector, selected)),
                  provenance=dict(first["provenance"], detector_sha256=new_detector))
    misses = [observation_id("session", rows[2*j+r]) for j, r in omitted]
    mask = dict(recipe=new_recipe, detector_sha256=new_detector, native_sha256=canonical_digest(masked),
                mask_sha256=canonical_digest(omitted), skipped_slots=omitted, lost_positive_ids=misses)
    owners = dict(c0=[[misses[0], 1, "conditional"]], fitted_c=[[misses[-1], 2, "predictive"]])
    return first, masked, mask, owners


def test_reopen_spends_union_and_preserves_native_candidate_order():
    first, masked, mask, owners = complete_inputs()
    reopened, audit, original = reopen(first, masked, owners, mask, "owner-receipt")
    assert audit["owner_union"] == 2 and audit["directly_omitted_by_arm"] == dict(c0=1, fitted_c=1)
    assert not audit["identical_arm_owner_ids"]
    assert [r["observation_id"] for r in audit["reopened"]] == [owners[a][0][0] for a in owners]
    assert reopened["delivery_clocks"] == first["delivery_clocks"]
    restored = {(r["visit"],r["radio"]) for r in audit["reopened"]}
    for old, cut, new in zip(first["source"]["probes"], masked["source"]["probes"], reopened["source"]["probes"], strict=True):
        assert new == (old if (old["visit_index"],old["receiver_id"]) in restored else cut)
    assert reopened["provenance"]["detector_sha256"] not in {
        first["provenance"]["detector_sha256"], masked["provenance"]["detector_sha256"]}
    graph = dict(graph_points=1, tracks=[dict(key="left", observation_ids=[owners["c0"][0][0]])])
    coverage = concentration(audit, original, graph)
    assert coverage["graph_tracks"] == [("left", 1)] and coverage["outside_graph"] == 1
    assert sum(coverage["issued_visit_deciles"]) == 2


def test_refuses_misattributed_owner_and_tampered_paid_lane():
    first, masked, mask, owners = complete_inputs()
    with pytest.raises(ValueError, match="genuine passed observation"):
        reopen(first, masked, dict(owners, c0=[["unseen", 3, "conditional"]]), mask, "owner-receipt")
    changed = deepcopy(masked)
    paid = changed["source"]["probes"][0]
    paid["candidates"][0]["candidate_rank"] = 7
    changed["source"]["analysis_manifest_sha256"] = analysis_digest(changed["source"], mask["detector_sha256"], changed["source"]["probes"])
    with pytest.raises(ValueError, match="changed an ordinary paid lane"):
        reopen(first, changed, owners, dict(mask, native_sha256=canonical_digest(changed)), "owner-receipt")


def test_price_uses_all_measured_short_calls_and_charges_every_rescued_lane():
    raw = dict(native=dict(native_calls=dict(short_primary=100), native_cpu_ns=dict(short_primary=100_000_000)))
    audit = dict(omitted_lanes=40, reopened=[{}]*10)
    previous = dict(per_short_cpu_s=0.001, fixed_nonnative_acquisition_cpu_s=1, measured_full_native_cpu_s=0.25)
    result = price(raw, audit, previous)
    assert result["remaining_omitted_calls"] == 30
    assert result["reopened_cpu_s"] == 0.010 and result["remaining_receiving_saving_cpu_s"] == 0.030
    assert result["modeled_total_acquisition_cpu_s"] == 1.22
