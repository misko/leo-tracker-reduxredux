import pytest

from sparse8_cfo_epoch import ALIAS_HZ, centroid, fit_past, observed_match
from sparse8_cfo_epoch_saved import correction_rows, graph_rows


def factor(epoch=100, fractional=.25, frequency=100., rank=0, margin=.2):
    return dict(integer_epoch_sample=epoch, fractional_epoch_offset_samples=fractional,
                fractional_tracking_cfo_hz=frequency, candidate_rank=rank,
                passed_fractional_margin_gate=True, fractional_margin=margin)


@pytest.mark.parametrize("value,full_count,shift_ms", [
    (factor(), 15, -6.666668),
    (factor(epoch=12_000), 14, -6.),
])
def test_native_aperture_centroid(value, full_count, shift_ms):
    short, n_short, scout_short = centroid(value, True)
    long, n_full, scout_long = centroid(value, False)
    assert (n_short, n_full) == (5, full_count)
    assert 1000*(short-long) == pytest.approx(shift_ms, abs=.0002)
    assert 1000*(scout_short-scout_long) == pytest.approx(-6., abs=.0002)


def test_past_slopes_exclude_future_current_and_other_receiver_same_visit():
    valid = [(float(t), t, 90.-7.*(t-10)+(t-10)**2) for t in range(3, 10)]
    donors = valid[:5]+[(7.5, 10, 1e5)]+valid[5:]+[(10., 9, 9e6), (10.5, 11, -9e6)]
    chosen = fit_past(10., 10, donors)
    assert chosen["slope_hz_per_s"] == pytest.approx(-7.)
    assert chosen["held_stock_prediction_hz"] == pytest.approx(90.)
    assert chosen["latest_donor_age_s"] == 1.


def test_signed_factors_are_separate_from_wrapped_controls():
    first = factor()
    same = factor(epoch=13_433, frequency=151.)
    aliased = factor(epoch=13_433, frequency=151.+ALIAS_HZ)
    missed = factor(epoch=13_438, frequency=151.)
    assert observed_match([first], [same]) == (51., 51., "signed")
    assert observed_match([first], [aliased])[1:] == (51., "wrapped-only")
    assert observed_match([first], [missed]) is None


def test_aperture_shift_keeps_stereo_anchors_and_cfo_and_changes_only_winner_time():
    probes = [dict(visit_index=visit, receiver_id=rx, valid_start_counter=1_000_000*visit,
                   edge="lower", channel=1, actual_rf_hz=1e10,
                   candidates=[factor(frequency=123.), factor(frequency=456., rank=1)])
              for visit in range(9) for rx in range(2)]
    native = dict(source=dict(probes=probes, session_id="signed"),
                  clock_anchor=dict(sample_counter=0), delivery_clocks=[], last_sample_counter=9_000_000,
                  provenance=dict(excluded_windows=[]))
    offsets = correction_rows(native)
    assert sum(offset == 0. for _, offset, _ in offsets.values()) == 4
    rows = [dict(observation_id=identity, receiver=1, channel=1, time_s=nominal,
                 measured_cfo_hz=cfo) for identity, (nominal, _, cfo) in offsets.items()]
    adjusted = graph_rows(rows, offsets)
    assert all(row["measured_cfo_hz"] == 123. for row in adjusted)
    for row in adjusted:
        nominal, offset, _ = offsets[row["observation_id"]]
        assert row["time_s"] == nominal+offset
    assert all("time_s" in row for row in rows)
    with pytest.raises(ValueError, match="original winners"):
        graph_rows(rows[:-1], offsets)
