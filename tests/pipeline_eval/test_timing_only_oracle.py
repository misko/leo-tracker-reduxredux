import pytest

from reports.ALGO08.v3.timing_only_oracle import (
    EPOCHS,
    LABELS,
    TICKS,
    distance,
    phase_offset,
    scope_order,
    scoped_bins,
    total_cpu,
)


def test_rows_keep_original_timing_order_even_when_the_finalists_repeat():
    order = [81, 2, 86, 5, 911, 7]
    assert scope_order(order, [7, 86, 86, 81], 0) == [81, 86, 7]
    assert scope_order(order, [7, 86, 86, 81], 4) == [81, 2, 86, 7]
    with pytest.raises(ValueError):
        scope_order(order, [10], 4)
    with pytest.raises(ValueError):
        scope_order(order, [7, 86, 81], 2)


def test_swept_windows_match_exact_integer_left_and_right_edges():
    phases = [TICKS - 1, 19992]
    for radius in (0, 4, 16, 64, 1024):
        assert scoped_bins(phases, radius) == {
            e for e in range(EPOCHS) if distance(e, phases) <= radius
        }


def test_phase_transfer_uses_original_counter_and_fractional_alignment():
    factor = (0, 13332, 1 / 3, -8000, 1, 0)
    assert phase_offset(factor, 10001, 10000) == 0
    assert phase_offset(factor, 10000, 10001) == TICKS - 6


def test_clock_totals_keep_all_arms_with_single_pass_input():
    clocks = iter(dict.fromkeys(LABELS, ticks) for ticks in (2, 3, 5))
    assert total_cpu(clocks) == dict.fromkeys(LABELS, 10)
