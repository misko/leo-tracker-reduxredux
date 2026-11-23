import pytest

from reports.ALGO08.v3.anchor_orbit_census import (
    ADC, GAP, PERIOD, STRIDE, WINDOW_BYTES, choose_anchors, holding, projected_cells, screen,
)


def factor(epoch, hz, rank=0):
    return dict(integer_epoch_sample=epoch, fractional_epoch_offset_samples=0.,
                fractional_tracking_cfo_hz=hz, fractional_margin=.2, candidate_rank=rank)


def visits(count):
    return [dict(visit_index=i, valid_start_counter=40_000_000_000_000 + i * ADC,
                 receiver_id=lane, channel=i % 2 + 1, actual_rf_hz=i % 2 + 1000.,
                 edge="lower", candidates=[])
            for i in range(count) for lane in (0, 1)]


def test_one_anchor_per_stereo_channel_block():
    rows = visits(40)
    anchors = choose_anchors(rows)
    assert anchors == choose_anchors(rows)
    for band in (range(0, 40, 2), range(1, 40, 2)):
        for offset in range(0, len(band), STRIDE):
            assert len(anchors.intersection(band[offset:offset + STRIDE])) == 1
    rows[1]["receiver_id"] = 0
    with pytest.raises(ValueError, match="paired stereo"):
        choose_anchors(rows)


def test_projected_cells_preserve_signed_frequency_and_phase_wrap():
    cell = projected_cells((0, (-6000, PERIOD - 3)), (2 * ADC, (-1000, 3)), ADC)
    assert cell == pytest.approx((-3500, 2750, [PERIOD], 16))
    assert projected_cells((0, (-6000, PERIOD - 3)), (2 * ADC, (20_000, 3)), ADC) is None
    with pytest.raises(ValueError, match="two-sided"):
        projected_cells((0, (-6000, 3)), (GAP + ADC + 1, (0, 3)), ADC)


def test_oracle_retains_repeated_carrier_and_retries_independent_residual():
    rows = visits(5)
    for i in (0, 2, 4):
        row = rows[2 * i]
        counter_phase = row["valid_start_counter"] * 3 % 40_000 // 3
        row["candidates"] = [factor((1000 - counter_phase) % PERIOD, -20_000.)]
    rows[4]["candidates"].append(factor(4560, 31_000., rank=1))
    result = screen(rows, {0, 4}, [[] for _ in rows], cpu=[11] * len(rows))
    stats = result["evidence"]["two_sided_cfo_and_phase"]["counts"]
    assert stats["nonanchor_reference_factors"] == 2
    assert stats["nonanchor_supported_factors"] == 1
    assert stats["nonanchor_supported_residuals"] == 0
    assert stats["oracle_full_lanes"] == 5
    assert stats["oracle_full_lane_cpu_ns"] == 55


def test_storage_counts_stereo_windows_once_and_skips_unbounded_lookahead():
    rows = visits(20)
    result = holding(rows, {0, 4, 5, 18})
    assert result["whole_record_pending_stereo_bytes"] == 16 * WINDOW_BYTES
    assert result["next_same_rf_anchor_peak_stereo_windows"] == 4
    assert result["next_same_rf_anchor_max_lookahead_s"] <= GAP / ADC
