import pytest

from reports.ALGO08.v3.eight_ms_primary import SHAPES, checked_shape
from reports.ALGO08.v3.eight_ms_primary_trial import arm_order, check_tail
from reports.ALGO08.v3.short_signed_trial import short_source


def test_five_origins_cover_latest_gate_but_six_do_not():
    shape = checked_shape(*SHAPES["8ms"])
    assert shape["last_origin"] == 53_333
    assert shape["first_unused_latest_confirmation_sample"] == 79_777
    assert shape["first_unused_fractional_sample"] == 69_579
    with pytest.raises(ValueError, match="lacks complete"):
        checked_shape(80_000, 6)


def test_five_frame_covariance_keeps_even_pair_allocation():
    before = """points = 200000; count = 14; early ? 7 : 2;
w->frames = reserve(w, count * w->width, sizeof(Sample));
"""
    odd = short_source("timing_first_receiver", before, *SHAPES["8ms"])
    assert "points = 80000" in odd and "count = 5" in odd
    assert "early ? count / 2 : 2" in odd
    assert "((count + 1) / 2) * 2 * w->width" in odd
    even = short_source("timing_first_receiver", before, *SHAPES["12ms"])
    assert "points = 120000" in even and "count = 8" in even
    assert "reserve(w, count * w->width, sizeof(Sample))" in even


def test_both_arm_orders_are_exercised_per_visit_and_repeat():
    assert arm_order(0, 0) == arm_order(1, 1) == ("12ms", "8ms")
    assert arm_order(0, 1) == arm_order(1, 0) == ("8ms", "12ms")


def test_tail_support_check_rejects_signed_factor_change():
    row = (0, 42, 0.25, -150.0, 0.5, 0.1)

    class Short:
        def run(self, *_args):
            return (row,), (0, 0)

    check_tail(Short(), (row,), object(), 1, -10.0)
    with pytest.raises(ValueError, match="post-aperture"):
        check_tail(Short(), (), object(), 1, -10.0)
