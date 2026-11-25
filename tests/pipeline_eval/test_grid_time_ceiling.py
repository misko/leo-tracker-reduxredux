import pytest

from reports.ALGO08.v3.grid_time_ceiling import decoder_targets, grid_seconds, price


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


def test_decoder_savings_apply_only_to_measured_decode_work():
    fix = dict(baseline=100, candidate=65, native=30, solver=20, grid=5,
               decode=10, decode_cpu=9, members=3)
    withheld = dict(baseline=40, candidate=20, native=0, solver=0, grid=0,
                    decode=0, decode_cpu=0, members=1)
    result = decoder_targets([fix, withheld], .8)
    assert result["members"] == 4
    assert result["pairs"] == 2
    assert result["map_and_native_1p5"]["seconds_above_half"] == pytest.approx(4)
    assert result["required_decode_fraction_with_native_1p5"]["both"] == pytest.approx(.4)
    assert result["native_targets"][0]["required_native_fraction_removed"] == pytest.approx(14/30)
    for value in (16, -1, float("nan")):
        with pytest.raises(ValueError):
            decoder_targets([fix | dict(decode=value)], .8)
