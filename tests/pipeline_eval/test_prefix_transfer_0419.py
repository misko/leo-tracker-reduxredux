from copy import deepcopy

import pytest

from reports.ALGO08.v3.prefix_transfer_0419 import (
    ARMS, CFO, GATE, MODES, certified_original, factor_contrast, observation_id, overlap,
)


def factor(rank=0, cfo=-18.5):
    return dict(candidate_rank=rank, fractional_tracking_cfo_hz=cfo, integer_epoch_sample=20,
                fractional_epoch_offset_samples=.03125, passed_fractional_margin_gate=True,
                fractional_exact_score=.5, fractional_control_score=.1, fractional_margin=.4)


def fixture():
    visits = [dict(sequence=j, sample_start=10**10 + j*200000, sample_end=10**10 + (j+1)*200000,
                   channel=2, actual_rf_hz=11_190_312_500, edge="upper", iq_sha256="sha256:" + "a"*64) for j in range(66)]
    lanes = [dict(visit_index=j, receiver_id=r, valid_start_counter=visit["sample_start"], channel=visit["channel"],
                  actual_rf_hz=visit["actual_rf_hz"], edge=visit["edge"], candidates=[factor()] if (j, r) in ((0, 0), (1, 0), (64, 0)) else [])
             for j, visit in enumerate(visits) for r in (0, 1)]
    source = dict(session_id="original", capture_mode="adaptive", sample_rate_hz=10_000_000, radio_id="signed-rx",
                  stream_generation="generation", probe_ms=20, timing=None, probes=lanes)
    packet = dict(clock_anchor=dict(sample_counter=visits[0]["sample_start"]), delivery_clocks=list(range(66)),
                  last_sample_counter=visits[-1]["sample_end"], source=source, provenance=dict(window_count=66,
                  processed_windows=66, invalid_capture=0, excluded_windows=[]))
    prefix = deepcopy(packet)
    prefix["source"].update(session_id="independent-prefix", probes=prefix["source"]["probes"][:128])
    prefix["provenance"].update(window_count=64, processed_windows=64)
    prefix["delivery_clocks"] = list(range(64))
    prefix["last_sample_counter"] = visits[63]["sample_end"]
    digest = observation_id(source["session_id"], lanes[0])
    roster = {role: {arm: {digest: [1234, "conditional"]} for arm in ARMS} for role in MODES}
    return packet, prefix, dict(visits=visits[:64]), roster


def test_match_original_absolute_counter_across_sessions_and_preserve_suffix():
    original, stock, witness, owners = fixture()
    mixed = deepcopy(stock)
    mixed["source"]["probes"][0]["candidates"][0][CFO] += 1.5
    mixed["source"]["probes"][1]["candidates"] = [factor()]
    mixed["source"]["probes"][2]["candidates"] = []
    audit, splice = overlap(original, stock, mixed, witness, owners)

    assert audit["can_splice"] and audit["changes"] == 3
    assert audit["signed_cfo"]["routed/fitted_c"]["median_hz"] == 1.5
    assert audit["membership"]["gained"]["total"]["installed/c0/unassigned_lane"] == 1
    assert audit["membership"]["lost"]["total"]["installed/c0/unassigned_lane"] == 1
    assert audit["owner_counts"]["installed"]["fitted_c"] == dict(first_64=1, full=1)
    assert splice[128:] == original["source"]["probes"][128:]


def test_archive_parity_allows_only_documented_score_roundoff():
    original, stock, witness, owners = fixture()
    archived = original["source"]["probes"][0]
    row = stock["source"]["probes"][0]
    row["candidates"][0]["fractional_margin"] += 1e-12
    assert certified_original(archived, row)
    audit, splice = overlap(original, stock, stock, witness, owners)
    assert audit["can_splice"] and audit["changes"] == 0 and splice[0] is archived
    row["candidates"][0][GATE] = False
    audit, splice = overlap(original, stock, stock, witness, owners)
    assert audit["checks"]["original_lane_differences"] == [(0, 0)] and splice is None


def test_reject_one_counter_drift_and_keep_multiplicity_ambiguous():
    original, stock, witness, owners = fixture()
    mixed = deepcopy(stock)
    mixed["source"]["probes"][0]["valid_start_counter"] += 1
    with pytest.raises(ValueError, match="coordinate"):
        overlap(original, stock, mixed, witness, owners)
    multiple = factor_contrast([factor(), factor(1)], [factor(), factor(1, -20.0)])
    assert len(multiple["retained"]) == len(multiple["ambiguous_before"]) == len(multiple["ambiguous_after"]) == 1
    assert multiple["gained"] == multiple["lost"] == []
