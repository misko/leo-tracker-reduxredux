import pytest

from reports.ALGO08.v3.short_phase_field_cost import FULL, SHORT, counts, timing, transfer


def test_counts_reserve_full_anchors_and_check_the_clock():
    native = dict(short_primary_sha256=SHORT, installed_sha256=FULL, native_calls={"full": 10, "short_primary": 7},
                  factors={"full": 9, "short_primary": 2}, native_cpu_ns={"full": 3_000_000_000,"short_primary": 4_000_000_000},
                  native_wall_ns={"full": 4_000_000_000, "short_primary": 5_000_000_000})
    row = dict(native_detector_process_cpu_s=7., native_detector_s=9.)
    assert counts(native, row) == dict(positive=2, empty=5, short_cpu=4., short_wall=5.)
    with pytest.raises(ValueError):
        counts(native, dict(row, native_detector_s=10.))
    with pytest.raises(ValueError):
        counts(dict(native, factors={"short_primary": 8}), row)


def test_transfer_prices_positive_and_empty_and_caps_the_scoped_time():
    row = dict(positive=1, empty=2, short_cpu=5., short_wall=4.)
    assert transfer(row, dict(positive=1e9, empty=.25e9)) == 1.5
    assert transfer(row, dict(positive=6e9, empty=1e9)) == 4.
    assert transfer(dict(row, short_cpu=2.), dict(positive=6e9, empty=1e9)) == 2.
    assert transfer(row, dict(positive=-1e9, empty=0)) == -1.


def test_speedup_uses_all_recordings_and_reports_residual():
    rows = [dict(stock_wall_s=10., actual_wall_s=7.), dict(stock_wall_s=2., actual_wall_s=1.)]
    got = timing(rows, [1., 0.])
    assert got["summed_speedup"] == pytest.approx(12/7)
    assert got["median_paired_speedup"] == pytest.approx(1/.55)
    assert got["remaining_seconds_to_half"] == 1.
