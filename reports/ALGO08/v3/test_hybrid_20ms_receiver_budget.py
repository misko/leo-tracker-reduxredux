"""Check hybrid clock arithmetic without a receiver or solver process."""

import pytest

from hybrid_20ms_receiver_budget import native_boundary, necessary_budget


def clock(wall, cpu):
    return dict(elapsed_s=wall, cpu_s=cpu)


def process(wall=10):
    return dict(clock(wall, 8), started_unix_ns=1_000_000_000, finished_unix_ns=11_000_000_000)


def test_single_cpu_boundary_uses_measured_total_and_wall_capacity():
    result = native_boundary(process(), 7_000_000_000, 9_000_000_000, one_cpu=True)
    assert result["write_elapsed_s"] == 6
    assert result["measured_cpu_s"] is None
    assert result["conditional_cpu_capacity_s"] == pytest.approx((3.99, 6.01))


@pytest.mark.parametrize("wall,one_cpu", [(10, False), (9.5, True)])
def test_cpu_capacity_needs_serial_bound_and_compatible_timebases(wall, one_cpu):
    result = native_boundary(process(wall), 7_000_000_000, 9_000_000_000, one_cpu=one_cpu)
    assert result["write_elapsed_s"] == 6
    assert result["conditional_cpu_capacity_s"] is None


def test_native_write_must_precede_terminal():
    with pytest.raises(ValueError, match="must precede"):
        native_boundary(process(), 10_000_000_000, 9_000_000_000)


def test_budget_separates_nested_publication_and_both_denominators():
    prefix = dict(write_elapsed_s=6, conditional_cpu_capacity_s=(4, 6))
    result = necessary_budget(clock(12, 10), clock(2, 1.5), clock(1, .5), clock(3.5, 2.5), clock(4, 3), prefix)
    assert result["half_baseline"] == clock(6, 5)
    assert result["all_other_at_most"] == clock(3, 3)
    assert result["receiver_allowance_if_whole_saved_block_charged"] == clock(2, 2)
    assert result["remaining_wall_after_observed_prefix_s"] == -3
    assert result["required_prefix_wall_saving_s"] == 3
    assert result["conditional_prefix_cpu_excess_s"] == 1


def test_budget_does_not_impute_a_missing_receiver_clock():
    result = necessary_budget(clock(8, 6), clock(2, 1.5), clock(1, .5), clock(3.5, 2.5), clock(4, 3), None)
    assert result["all_other_at_most"] == clock(1, 1)
    assert "required_prefix_wall_saving_s" not in result
    assert "conditional_prefix_cpu_excess_s" not in result


def test_budget_rejects_a_nested_sum_larger_than_its_enclosing_stage():
    with pytest.raises(ValueError, match="disjoint solve"):
        necessary_budget(clock(12, 10), clock(3, 2), clock(1, 1), clock(3.5, 3), clock(4, 3), None)
