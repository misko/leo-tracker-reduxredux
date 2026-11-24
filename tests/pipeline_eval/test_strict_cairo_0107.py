import pytest

from reports.ALGO08.v3.strict_cairo_0107 import cohort, expenses


def times(wall, cpu=None):
    return dict(elapsed_s=wall, cpu_s=wall if cpu is None else cpu, exit_code=0)


def test_paid_costs_keep_historical_conversion_and_current_setup_separate():
    original_conversion = dict(total_including_compiler_and_verification={"wall_ns": 350_000_000, "cpu_ns": 300_000_000},
                               compiler={"compiler_cpu_s": .02})
    cost = expenses(times(.5, .49), times(1.5), times(.10, .07), times(.02, .02), original_conversion)

    assert cost["scopes"]["child"] == (.5, .49)
    assert cost["scopes"]["ready"] == pytest.approx((.52, .51))
    assert cost["scopes"]["first"] == pytest.approx((.87, .83))
    assert cost["scopes"]["first_with_common"] == pytest.approx((.97, .90))


def test_paired_median_and_summed_ratio_are_separately_gated():
    tiny = dict(candidate=times(1), stock=times(2), scopes={"ready": (1, 1)})
    weak = dict(candidate=times(9), stock=times(12), scopes={"ready": (9, 9)})

    ready = cohort(tiny, weak)["ready"]

    assert ready["timing"]["elapsed_s"]["median_ratio"] == .625
    assert ready["timing"]["elapsed_s"]["summed_ratio"] == pytest.approx(10/14)
    assert ready["gates"]["1.6x"] == {"median": True, "sum": False, "both": False}
    with pytest.raises(ValueError, match="same paid scope"):
        cohort(tiny, weak | {"scopes": {"first": (10, 10)}})
