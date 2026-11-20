from copy import deepcopy

import pytest

from tools.pipeline_eval.qualification.iq_schedule import native_durations
from tools.pipeline_eval.qualification.iq_schedule_worker import (
    native_stub,
    scheduled,
    select_document,
    verify_effective,
)


def document():
    probes = [
        dict(visit_index=v, channel=1 + v % 8, receiver_id=rx, candidates=[dict(value=v + rx)])
        for v in range(32)
        if v != 1
        for rx in (0, 1)
    ]
    return dict(
        source={"probes": probes, "analysis_manifest_sha256": "full-identity"},
        provenance={
            "run_id": "full-run",
            "window_count": 32,
            "processed_windows": 31,
            "excluded_windows": [{"visit": 1}],
        },
        delivery_clocks=list(range(32)),
    )


def captured():
    full = document()
    emitted = deepcopy(full)
    emitted["source"]["analysis_manifest_sha256"] = "fresh-identity"
    emitted["provenance"]["run_id"] = "fresh-run"
    for row in emitted["source"]["probes"]:
        if not scheduled(row["visit_index"], row["channel"]):
            row["candidates"] = []
    return full, emitted


def test_empty_dual_rx_envelopes_produce_the_canonical_effective_document():
    full, emitted = captured()
    expected, coverage = select_document(full)
    effective, counts, normalization = verify_effective(emitted, full)
    assert effective == expected and counts == coverage
    assert len(effective["delivery_clocks"]) == 32
    assert effective["provenance"]["excluded_windows"] == [{"visit": 1}]
    assert set(normalization) == {"source.analysis_manifest_sha256", "provenance.run_id"}
    assert emitted["source"]["analysis_manifest_sha256"] == "fresh-identity"
    assert native_stub((0, 1)) == {
        "rows": [
            {"receiver_id": 0, "candidates": []},
            {"receiver_id": 1, "candidates": []},
        ]
    }


def test_parity_rejects_any_change_to_retained_factors_or_clock():
    full, emitted = captured()
    emitted["delivery_clocks"][1] = 999
    with pytest.raises(ValueError, match="differs beyond"):
        verify_effective(emitted, full)
    full, emitted = captured()
    row = next(x for x in emitted["source"]["probes"] if x["candidates"])
    row["candidates"][0]["value"] = 999
    with pytest.raises(ValueError, match="native retained"):
        verify_effective(emitted, full)


def test_durations_keep_the_original_individual_20ms_gate():
    trace = dict(
        raw=dict(
            capture_seconds=300,
            raw_lanes=[
                dict(
                    native_timings_s=[
                        (0.019, 0.011),
                        (0.020, 0.011),
                        (0.030, 0.020),
                        (0.071, 0.025),
                    ]
                )
            ],
        ),
        position=None,
    )
    observed = native_durations(trace)
    assert observed["physical_calls"] == 4
    assert observed["wall_at_most_20ms"] == 2
    assert observed["wall_ms"] == pytest.approx(dict(mean=35, median=25, p95=71))
