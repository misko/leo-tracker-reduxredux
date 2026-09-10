from dataclasses import replace

import pytest

from tests.scanner.fair_admission_harness import Geometry
from tools.scanner_sampled_admission_model import simulate


def visits(origin=0):
    return [Geometry(origin + i * 300000, origin + (i + 1) * 300000, i % 8) for i in range(40)]


@pytest.mark.parametrize("cost", [75, 170, 210])
def test_integer_source_translation_and_exact_reproducibility(cost):
    small = simulate(visits(), 2500000, [cost] * 40)
    large = simulate(visits(2**53 + 347), 2500000, [cost] * 40)
    assert small == large
    assert len({c["visit"] for c in small["checks"]}) == len(small["checks"])
    assert {c["target"] for c in small["checks"]} == set(range(8))


@pytest.mark.parametrize(
    "fault",
    [
        "empty",
        "cost_count",
        "cost_nan",
        "cost_zero",
        "cost_limit",
        "rate",
        "block_zero",
        "block_float",
        "jitter_empty",
        "jitter_negative",
        "jitter_limit",
        "overlap",
        "dwell",
        "target",
    ],
)
def test_invalid_scenarios_fail_before_iteration(fault):
    geometry, costs, rate, block, jitter = visits(), [170] * 40, 2500000, 20, (0,)
    if fault == "empty":
        geometry = []
    if fault == "cost_count":
        costs = [170]
    if fault == "cost_nan":
        costs[0] = float("nan")
    if fault == "cost_zero":
        costs[0] = 0
    if fault == "cost_limit":
        costs[0] = 450
    if fault == "rate":
        rate = 0
    if fault == "block_zero":
        block = 0
    if fault == "block_float":
        block = 0.5
    if fault == "jitter_empty":
        jitter = ()
    if fault == "jitter_negative":
        jitter = (-1,)
    if fault == "jitter_limit":
        jitter = (20,)
    if fault == "overlap":
        geometry[1] = geometry[0]
    if fault == "dwell":
        geometry[0] = replace(geometry[0], end=1)
    if fault == "target":
        geometry[0] = replace(geometry[0], target=8)
    with pytest.raises(ValueError):
        simulate(geometry, rate, costs, block_ms=block, owner_jitter_ms=jitter)
