from itertools import islice

from tools.pipeline_eval.qualification.mixed_duty_cost import route_cost
from tools.pipeline_eval.variants import mixed_duty as policy


def test_credit_prefixes_and_same_count_without_candidate_input():
    n = 6 * policy.PERIOD + policy.LAST_OFFSET
    metadata = [(2 * i, 1 + i % 8) for i in range(n)]
    picked = [list(policy.route(iter(metadata), key)) for key in policy.METHODS]
    assert [len(r) for r in picked] == [6, 6]
    assert [r["channel"] for r in picked[0]] == [1, 5, 2, 6, 3, 7]
    assert len({r["channel"] for r in picked[1]}) == 1
    for route, mode in zip(picked, policy.METHODS, strict=True):
        for prefix in (0, 1023, 1024, 1025, 2070, n):
            from_prefix = list(policy.route(islice(metadata, prefix), mode))
            assert from_prefix == [r for r in route if r["ordinal"] <= prefix]
            assert len(from_prefix) <= prefix // policy.PERIOD


def test_unavailable_lane_cannot_borrow_or_wait_past_limit():
    missing = ((i, 8) for i in range(policy.PERIOD + policy.LAST_OFFSET))
    (routed,) = policy.route(missing, "rotating")
    assert routed == dict(visit=1038, ordinal=1039, channel=8, target=1, credit=1)
    truncated = [(i, 8) for i in range(policy.PERIOD + policy.LAST_OFFSET - 1)]
    assert list(policy.route(truncated, "rotating")) == []


def test_cost_model_subtracts_exact_avoided_cpu_and_counts_wall_deadlines():
    measured_wide = {0: (9, 12), 1: (21, 40), 2: (14, 20)}
    result = route_cost(measured_wide, {0}, 1, 110, 50, 170)
    assert result["routed_wide_counterfactual_cpu_ms"] == 9
    assert result["estimated_cpu_ms"] == (21 + 14 + 1 + 110) / 3
    assert result["box_low_cpu_ms"] == (21 + 14 + 1 + 50) / 3
    assert result["box_high_cpu_ms"] == (21 + 14 + 1 + 170) / 3
    assert result["actual_wide_wall_le_20ms"] == 2
    assert result["modeled_mixed_wall_le_20ms"] == 1
