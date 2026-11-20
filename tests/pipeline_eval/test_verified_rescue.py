from collections import Counter
from types import SimpleNamespace

import numpy as np
import pytest

from tools.pipeline_eval.qualification import (
    verified_rescue,
    verified_rescue_raw,
    verified_rescue_stage,
)
from tools.pipeline_eval.variants.pilot_confirmation import PilotEvidence


def test_equal_count_control_is_order_independent_in_each_receiver_band():
    rows = [
        dict(visit=i, lane=lane, channel=channel, edge="lower", passed=(i < lane + channel))
        for lane in (0, 1)
        for channel in (1, 2)
        for i in range(12 * (channel - 1), 12 * channel)
    ]
    a = verified_rescue.matched_count("one", rows)
    assert a == verified_rescue.matched_count("one", list(reversed(rows)))
    assert Counter((r["lane"], r["channel"]) for r in rows if r["passed"]) == Counter(
        (r["lane"], r["channel"]) for r in rows if (r["visit"], r["lane"]) in a
    )


def test_only_a_selected_new_positive_replaces_the_whole_stock_packet():
    peak = dict(passed_fractional_margin_gate=True, fractional_margin=0.05, candidate_rank=1)
    old = {"candidates": []}
    new = {"candidates": [peak]}
    assert verified_rescue.choose_packet(old, new, True) is new
    assert verified_rescue.choose_packet(new, old, False) is new
    with pytest.raises(ValueError, match="negative packet"):
        verified_rescue.choose_packet(new, new, True)
    with pytest.raises(ValueError, match="negative packet"):
        verified_rescue.choose_packet(old, old, True)


def test_raw_witness_receives_exact_time_frequency_and_physical_lane():
    window = SimpleNamespace(
        sequence=8,
        iq_sha256="wave",
        acquisition=dict(global_visit=72, sample_start=99),
        target=dict(channel=3, edge="upper"),
        samples=np.empty(0),
    )
    winner = dict(
        integer_epoch_sample=456,
        fractional_epoch_offset_samples=-0.7,
        fractional_tracking_cfo_hz=-148341.0,
        fractional_margin=0.12,
    )
    request = dict(
        sequence=8,
        visit=72,
        counter=99,
        iq_sha256="wave",
        channel=3,
        edge="upper",
        gains=[dict(lane=1, winner=winner)],
    )

    def confirm(samples, candidates):
        assert samples is window.samples and not candidates[0]["candidates"]
        assert candidates[1]["receiver_id"] == 1
        probe = candidates[1]["candidates"][0]
        assert probe["epoch"] == 456 and probe["fractional_epoch"]["offset_samples"] == -0.7
        assert probe["fractional_epoch"]["tracking_cfo_hz"] == -148341
        return {(1, 0): PilotEvidence(15, (4.0, 3.0), 4.9, True)}

    measured = verified_rescue_raw.measure_window(window, request, {"upper": confirm})
    assert measured["probes"][0]["lane"] == 1 and measured["probes"][0]["passed"] is True
    with pytest.raises(ValueError, match="raw samples"):
        verified_rescue_raw.measure_window(window, dict(request, channel=4), {"upper": confirm})


def test_stage_uses_the_full_instrument_denominator():
    rows = [
        dict(label="capture_winner", passed=True),
        dict(label="other_capture_candidate", passed=False),
        dict(label="different_family", passed=False),
        dict(label="capture_negative", passed=True),
    ]
    assert verified_rescue_stage.row_counts(rows) == dict(
        proposed=4,
        verified=2,
        original_matched=2,
        original_matched_verified=1,
        other=2,
        other_verified=1,
    )
