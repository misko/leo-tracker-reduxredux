"""Exercise capture support and causality for the fixed streaming prefix."""

import json
from copy import deepcopy
from hashlib import sha256

import pytest

from tools.pipeline_eval.qualification import contiguous_prefix_raw as raw
from tools.pipeline_eval.variants.contiguous_prefix import audit_prepared, restrict

RATE = 10_000_000
ORIGIN = 23_000_000
WINDOW = RATE // 50
CUTOFF = ORIGIN + 180 * RATE


@pytest.fixture
def capture():
    def clock(seconds):
        elapsed = round(seconds * 1e9)
        return dict(monotonic_ns=1_000_000_000 + elapsed, realtime_ns=10_000_000_000 + elapsed)

    def probes(visit, start):
        return [
            dict(
                visit_index=visit,
                receiver_id=receiver,
                channel=visit % 8 + 1,
                valid_start_counter=start,
                probe_start_ms=0,
                probe_index=0,
                candidates=[dict(value=10 * visit + receiver)],
            )
            for receiver in (0, 1)
        ]

    return dict(
        source=dict(
            probes=[
                *probes(0, ORIGIN),
                *probes(2, CUTOFF - WINDOW),
                *probes(3, CUTOFF),
                *probes(4, CUTOFF + 120 * RATE),
            ],
            sample_rate_hz=RATE,
            probe_ms=20,
            analysis_manifest_sha256="frozen-analysis",
        ),
        provenance=dict(
            window_count=5,
            processed_windows=4,
            invalid_capture=1,
            excluded_windows=[
                dict(visit=1, sample_start=ORIGIN + 3 * WINDOW, sample_end=ORIGIN + 4 * WINDOW)
            ],
        ),
        clock_anchor=dict(sample_counter=ORIGIN, before=clock(0), after=clock(0.15)),
        delivery_clocks=[clock(s) for s in (0.15, 0.20, 180.08, 180.15, 300.17)],
        last_sample_counter=CUTOFF + 120 * RATE + WINDOW,
    )


def test_prefix_keeps_complete_extent_inclusive_and_preserves_absolute_clocks(capture):
    before = deepcopy(capture)
    view, receipt = restrict(capture, prefix=True)

    assert capture == before
    assert view["clock_anchor"] == capture["clock_anchor"]
    assert view["last_sample_counter"] == CUTOFF
    assert view["delivery_clocks"] == capture["delivery_clocks"][:3]
    assert view["source"]["probes"] == capture["source"]["probes"][:4]
    assert (
        view["source"]["analysis_manifest_sha256"] != capture["source"]["analysis_manifest_sha256"]
    )
    assert view["provenance"]["excluded_windows"] == capture["provenance"]["excluded_windows"]
    assert receipt["next_sample_end_counter"] == CUTOFF + WINDOW
    assert receipt["last_input_sample_s"] == 180
    assert receipt["last_input_delivery_elapsed_s"] == [179.93, 180.08]
    assert restrict(capture, prefix=False)[0] == capture


def test_prefix_rejects_missing_receiver_and_wrong_channel(capture):
    capture["source"]["probes"][3]["receiver_id"] = 0
    with pytest.raises(ValueError, match="original paired probes"):
        restrict(capture, prefix=True)
    capture["source"]["probes"][3]["receiver_id"] = 1
    capture["source"]["probes"][3]["channel"] = 4
    with pytest.raises(ValueError, match="eight-channel cadence"):
        restrict(capture, prefix=True)


def test_prefix_drops_window_that_straddles_the_cutoff(capture):
    for probe in capture["source"]["probes"]:
        if probe["visit_index"] == 2:
            probe["valid_start_counter"] -= WINDOW
        if probe["visit_index"] == 3:
            probe["valid_start_counter"] -= WINDOW // 2

    restricted, receipt = restrict(capture, prefix=True)

    assert [p["visit_index"] for p in restricted["source"]["probes"]] == [0, 0, 2, 2]
    assert receipt["last_sample_counter"] == CUTOFF - WINDOW
    assert receipt["next_sample_end_counter"] == CUTOFF + WINDOW // 2


def test_rebuilt_evidence_requires_causal_tracks_and_orbits():
    prepared = dict(
        tracks=dict(
            metadata=dict(duration_s=180, causal_cutoff_utc_ns=123_000),
            observations=[dict(time_s=179.99)],
            tracks=[dict(end_s=179.99)],
        ),
        sky=dict(
            metadata=dict(candidate_count=1, cutoff_utc_ns=123_000),
            nominal_elements={
                45: dict(provenance=dict(collected_utc_ns=123_000, element_epoch_utc_ns=120_000))
            },
            selected_tle="archived catalogue",
        ),
    )
    assert audit_prepared(prepared)["latest_catalogue_authority_utc_ns"] == 123_000

    prepared["tracks"]["tracks"][0]["end_s"] = 180.05
    with pytest.raises(ValueError, match="retained capture end"):
        audit_prepared(prepared)
    prepared["tracks"]["tracks"][0]["end_s"] = 179.99

    prepared["sky"]["nominal_elements"][45]["provenance"]["collected_utc_ns"] = 123_001
    with pytest.raises(ValueError, match="capture-start causal cutoff"):
        audit_prepared(prepared)


def test_raw_scope_reads_complete_prefix_chunks_and_records_boundary_tail(monkeypatch):
    manifest = json.dumps(
        dict(
            window_count=8,
            chunks=[
                dict(first_sequence=0, window_count=4),
                dict(first_sequence=4, window_count=4),
            ],
        )
    ).encode()
    monkeypatch.setattr(raw, "_read_prefix", lambda path, limit: manifest)
    segments = [dict(path=str(i), sha256=sha256(manifest).hexdigest()) for i in range(3)]

    selected = raw.scopes(segments, 14)

    assert [row["stop_sequence"] for row in selected] == [8, 6]
    assert [row["archive_boundary_tail"] for row in selected] == [0, 2]
    with pytest.raises(ValueError, match="outside the frozen recording"):
        raw.scopes(segments, 25)
