import pytest

from reports.ALGO08.v3.blind_cpu_wait_budget import compare, wait_limit


def row(cpu, waited=20, minimum_wait=1, elapsed=100):
    return {"modeled_cpu_s": cpu, "stock_wait_s": waited, "saved_wait_s": minimum_wait,
            "stock_elapsed_s": elapsed}


def test_impossible_and_unlimited_wait():
    assert wait_limit([row(50)]) is None
    assert wait_limit([row(29)]) == 1
    assert compare([row(39)], 0)["summed_speedup"] == 2.5


def test_summed_gate_binds_before_median():
    rows = [row(15), row(40), row(80)]
    assert wait_limit(rows) == pytest.approx(0.25)
    assert compare(rows, 0.25)["paired_median_speedup"] > 2


def test_median_gate_can_bind_first():
    rows = [row(1), row(40), row(40)]
    assert wait_limit(rows) == pytest.approx(0.5)
    assert compare(rows, 0.5)["summed_speedup"] > 2
