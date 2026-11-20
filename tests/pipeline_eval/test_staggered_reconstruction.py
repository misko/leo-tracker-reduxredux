from copy import deepcopy

import pytest

from tools.pipeline_eval.__main__ import encoded
from tools.pipeline_eval.qualification.staggered_reconstruction_results import (
    METHODS,
    pair_effects,
    scores,
)
from tools.pipeline_eval.scoring import ARMS, ROLES
from tools.pipeline_eval.variants.staggered_reconstruction import assemble


def parent(frequency, invalid=(2,)):
    tuned = (1, 2, 1, 3, 2, 1)
    probes = [
        dict(
            visit_index=visit,
            receiver_id=rx,
            channel=channel,
            edge="upper",
            actual_rf_hz=float(channel * 100),
            valid_start_counter=10000 + visit,
            candidates=[
                dict(
                    passed_fractional_margin_gate=True,
                    fractional_margin=0.1,
                    candidate_rank=0,
                    fractional_tracking_cfo_hz=frequency + 10 * visit + rx,
                )
            ],
        )
        for visit, channel in enumerate(tuned)
        if visit not in invalid
        for rx in range(2)
    ]
    return dict(
        schema_version=1,
        clock_anchor={},
        delivery_clocks=list(range(len(tuned))),
        last_sample_counter=20000,
        provenance=dict(
            window_count=len(tuned),
            processed_windows=len(probes) // 2,
            invalid_capture=len(invalid),
            rf_mapping_authorities=["fixture"],
            excluded_windows=[{"visit": visit} for visit in invalid],
        ),
        source=dict(
            session_id="A",
            input_manifest_sha256="B",
            raw_recording_authority_digest="C",
            sample_rate_hz=10_000_000,
            probe_ms=20,
            radio_id="D",
            stream_generation="E",
            capture_mode="fixture",
            qualified=True,
            probes=probes,
        ),
    )


def test_one_fifth_lane_per_rf_and_no_parity_for_invalid_visit():
    stock, fifth = parent(1000), parent(2000)
    before = deepcopy((stock, fifth))
    # Channel 3 maps to the same recorded integer center as channel 1.
    rf = {(1, "upper"): 100, (2, "upper"): 200, (3, "upper"): 100}
    out, receipt, counts = assemble(stock, fifth, rf, encoded)
    assert [(r["visit"], r["fifth_lane"]) for r in receipt] == [
        (0, 0),
        (1, 0),
        (3, 1),
        (4, 1),
        (5, 0),
    ]
    assert counts["fifth_by_rf"] == {"100": [2, 1], "200": [1, 1]}
    assert counts["invalid_visits"] == 1 and counts["staggered_positive"] == 10
    for offset, row in enumerate(receipt):
        lane = row["fifth_lane"]
        assert out[2 * offset + lane] is fifth["source"]["probes"][2 * offset + lane]
        assert out[2 * offset + 1 - lane] is stock["source"]["probes"][2 * offset + 1 - lane]
    assert (stock, fifth) == before


def test_rejects_divergent_clock_packet_and_incomplete_recording():
    stock, fifth = parent(1000), parent(2000)
    rf = {(1, "upper"): 100, (2, "upper"): 200, (3, "upper"): 300}
    altered = deepcopy(fifth)
    altered["source"]["raw_recording_authority_digest"] = "another manifest"
    with pytest.raises(ValueError, match="clock authority"):
        assemble(stock, altered, rf, encoded)
    altered = deepcopy(fifth)
    altered["source"]["probes"][0]["valid_start_counter"] += 1
    with pytest.raises(ValueError, match="support or receiver"):
        assemble(stock, altered, rf, encoded)
    for obj in (stock, fifth):
        obj["source"]["probes"] = obj["source"]["probes"][:-2]
    with pytest.raises(ValueError, match="each physical"):
        assemble(stock, fifth, rf, encoded)


def test_scheduled_timeout_keeps_both_arms_and_has_no_paired_delta():
    ident = "test-1"
    refs = {
        ident: dict(
            truth=[0.0, 0.0],
            reference={role: {arm: dict(error_km=1.0) for arm in ARMS} for role in ROLES},
        )
    }
    complete = dict(
        status="ok",
        arms={arm: dict(latlon=[0.0, 0.0], rf_rms_hz=40.0) for arm in ARMS},
        metrics={},
    )
    timeout = dict(status="timed_out", metrics={})
    data = [
        dict(id=ident, method=method, result=result)
        for method, result in zip(METHODS, (complete, complete, timeout), strict=True)
    ]
    table = scores(data, refs)
    treatment = [row for row in table if row["method"] == METHODS[-1]]
    assert [row["status"] for row in treatment] == ["timed_out", "timed_out"]
    assert [row["error_km"] for row in treatment] == [None, None]
    differences = pair_effects(table, [ident])
    assert [row["error_vs_stock_km"] for row in differences] == [None, None]
    assert [row["conditional_rms_vs_fifth_hz"] for row in differences] == [None, None]
