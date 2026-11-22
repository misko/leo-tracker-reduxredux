from copy import deepcopy

import pytest

from tools.pipeline_eval.variants.carrier_continuation import Continuation
from tools.pipeline_eval.variants.experimental.channel_lane import project, time_arcs


def sample():
    rows = [dict(visit_index=i, channel=i%2+1, valid_start_counter=i*200000, actual_rf_hz=(i%2+1)*100,
                 receiver_id=rx, candidates=[dict(frequency=i+rx)]) for i in range(12) for rx in (1, 0)]
    return dict(source=dict(probes=rows, analysis_manifest_sha256="original"),
                provenance=dict(processed_windows=12))


def test_two_assignments_partition_complete_histories_without_changing_evidence():
    native = sample()
    original = deepcopy(native)
    a, b = [project(native, flip) for flip in (0, 1)]
    assert native == original
    assert a["source"]["analysis_manifest_sha256"] != b["source"]["analysis_manifest_sha256"]
    assert a["provenance"]["processed_windows"] == 12
    for row_a, row_b, first, second in zip(a["source"]["probes"], b["source"]["probes"],
            original["source"]["probes"][::2], original["source"]["probes"][1::2], strict=True):
        assert row_a["receiver_id"] == row_a["channel"] % 2
        assert row_a["receiver_id"] != row_b["receiver_id"]
        assert (row_a, row_b) in ((first, second), (second, first))


def test_projection_rejects_incomplete_or_mismatched_pairs():
    native = sample()
    native["source"]["probes"][1]["actual_rf_hz"] += 1
    with pytest.raises(ValueError, match="same visit"):
        project(native, 0)
    native["source"]["probes"].pop()
    with pytest.raises(ValueError, match="complete"):
        project(native, 1)


def test_alternate_channels_preserve_both_antennas_and_entire_history():
    native = sample()
    for flip in (0, 1):
        result = project(native, flip, "stereo-alternate-channels")
        assert result["source"]["probes"] == [p for p in native["source"]["probes"]
                                               if p["channel"] % 2 == flip]
        assert result["provenance"]["processed_windows"] == 6


def test_time_arcs_include_start_end_and_charge_unpublished_history():
    native = sample()
    native.update(clock_anchor={"sample_counter": 9000}, last_sample_counter=120_009_000)
    native["source"]["sample_rate_hz"] = 10_000_000
    for r in native["source"]["probes"]:
        r["valid_start_counter"] = 9000 + 10_000_000 * r["visit_index"]
    result = time_arcs(native)
    assert {r["visit_index"] for r in result["source"]["probes"]} == {0, 1, 2, 9, 10, 11}
    # On this short example the remaining six visits are all inside the warmup.
    assert result["provenance"]["warmup_lanes"] == 12


def test_warmup_recreates_full_continuation_on_the_published_arcs():
    duration = 600_000_000
    def replay(warm):
        picker = Continuation()
        selected = []
        for visit in range(240):
            counter = visit * 2_500_000
            published = 4*counter < duration or 4*counter >= 3*duration
            if not published and (warm is None or counter < 3*duration//4 - warm):
                continue
            for rx in (0, 1):
                candidates = [dict(fractional_tracking_cfo_hz=1000+rx+visit, candidate_rank=1, fractional_margin=.2)]
                row = dict(channel=visit%3, receiver_id=rx, actual_rf_hz=10_700_000_000+visit%3,
                           valid_start_counter=counter, candidates=candidates)
                _, keep, _ = picker.select(row)
                if published:
                    selected.append((visit, rx, keep))
        return selected
    all_visits = replay(duration)
    assert replay(80_000_000) == all_visits
    assert replay(None) != all_visits
