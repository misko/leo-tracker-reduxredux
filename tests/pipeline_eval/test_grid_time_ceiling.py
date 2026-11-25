import pytest

from reports.ALGO08.v3.grid_time_ceiling import grid_seconds, price


def test_removing_the_grid_preserves_the_rest_of_the_solver_and_all_attempts():
    rows = [dict(baseline=100, candidate=66, native=30, solver=20, grid=5),
            dict(baseline=40, candidate=21, native=3, solver=0, grid=0)]
    result = price(rows, 1.5, 0.)
    assert result["seconds_above_half"] == pytest.approx(1.)
    assert result["summed_speedup"] == pytest.approx(140/71)
    assert result["paired_median_speedup"] == pytest.approx(1 / ((.51 + .5)/2))
    assert result["additional_non_grid_solver_fraction"] == pytest.approx(1/15)


def test_zero_grid_requires_an_actual_nonpublication():
    clock = dict(complete=True, points=179, clock=dict(elapsed_ns=4000, cpu_ns=3000))
    assert grid_seconds(clock, "complete", .000003) == .000004
    assert grid_seconds(None, "withheld", 0.) == 0.
    for grid, outcome, cpu in ((None, "complete", 0.), (None, "withheld", .1),
                               (clock, "complete", 0.), (dict(clock, points=178), "complete", .000003)):
        with pytest.raises(ValueError):
            grid_seconds(grid, outcome, cpu)


def test_rejects_overlapping_or_out_of_scope_clocks():
    row = dict(baseline=100, candidate=50, native=20, solver=28, grid=10)
    for changed in (dict(grid=29), dict(native=23), dict(grid=-1)):
        with pytest.raises(ValueError):
            price([row | changed], 1.5, 0.)
