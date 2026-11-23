from hashlib import sha256
from pathlib import Path
import sys

import pytest


RESEARCH = Path(__file__).resolve().parents[2] / "reports/ALGO08/v3"
sys.path.insert(0, str(RESEARCH))
try:
    from full_confirmed_future import RAW_STEREO_BYTES, confirm, history_plan
finally:
    sys.path.remove(str(RESEARCH))


def factor(cfo, epoch=100, rank=0):
    return dict(candidate_rank=rank, fractional_tracking_cfo_hz=cfo,
                integer_epoch_sample=epoch, fractional_epoch_offset_samples=.25,
                passed_fractional_margin_gate=True, fractional_margin=.9)


def witness(factors):
    return dict(clock_anchor={"fixed": True}, source=dict(session_id="recording",
        raw_recording_authority_digest="raw", input_manifest_sha256="manifest",
        probes=[dict(visit_index=visit, receiver_id=rx, valid_start_counter=visit*10_000_000,
                     channel=1, actual_rf_hz=11e9, edge="lower",
                     candidates=[] if factor is None else [factor])
                for visit, pair in enumerate(factors) for rx, factor in enumerate(pair)]))


def row(visit, rx, cfo):
    oid = "sha256:" + sha256(f"recording:{rx}:{visit*10_000_000}".encode()).hexdigest()
    return dict(observation_id=oid, measured_cfo_hz=cfo)


def test_preserve_full_and_matched_short_measurements_without_substitution():
    shorter = witness([(factor(9), None), (factor(-20, 0), factor(-20)),
                       (factor(-20), factor(20))])
    stock = witness([(None, None), (factor(-270, 13_332), factor(231)),
                     (factor(-20, rank=1), None)])
    prospective = [row(0, 0, 9), row(1, 0, -20), row(1, 1, -20), row(2, 0, -20), row(2, 1, 20)]
    result, audit = confirm(stock, shorter, prospective)
    assert result == prospective[:2] and result[1] is prospective[1]
    assert audit["counts"] == dict(future=5, already_full=1, short_future=4, confirmed_short=1,
                                    mismatched_cfo=1, stock_selected_residual=1, missing_stock_selected_factor=1)
    assert audit["history"]["target_visits"] == 2
    assert audit["history"]["target_only_stereo_decoded_bytes"] == 2*RAW_STEREO_BYTES


def test_metadata_changes_and_missing_ids_are_rejected():
    short = witness([(factor(0), None)])
    different = witness([(factor(0), None)])
    different["source"]["probes"][0]["edge"] = "upper"
    with pytest.raises(ValueError, match="lane or valid start"):
        confirm(different, short, [])
    with pytest.raises(ValueError, match="did not match"):
        confirm(short, short, [row(9, 0, 12)])


def test_price_union_of_exact_lane_history_without_reading_factors():
    probes = witness([(None, None)]*14)["source"]["probes"]
    for probe in probes:
        del probe["candidates"]
    record = history_plan(probes, {(12, 0), (13, 0)}, {8})
    assert record["history_context_lanes"] == 8
    assert record["history_target_and_context_visits"] == 10
    assert record["prefix_admitted_full_visits"] == 14
    assert record["history_stereo_visits_with_retained_full_vectors"] == 9
