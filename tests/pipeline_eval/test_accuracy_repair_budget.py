from itertools import combinations
from math import fsum
from statistics import median

import pytest

from reports.ALGO08.v3.accuracy_repair_budget import acceptable_pair, repair_budget


def row(seconds, zero, fitted, fix=True):
    return dict(elapsed_s=seconds, c0_fix=fix, fitted_c_fix=fix, c0_error_km=zero, fitted_c_error_km=fitted)


def test_fix_and_excess_must_both_pass_in_each_arm():
    a = row(2., 1., 1.)
    assert acceptable_pair(a, row(1., 1.25, 1.25), .25)
    assert not acceptable_pair(a, row(1., 1.26, 0.), .25)
    assert not acceptable_pair(a, row(1., None, None, False), .25)
    assert acceptable_pair(row(1., None, None, False), a, 0.)
    assert not acceptable_pair(row(1., None, None), row(1., None, None, False), 0.)


@pytest.mark.parametrize("n", (6, 7))
@pytest.mark.parametrize("fraction", (0., .5, .75, 1.))
def test_bounds_include_exhaustive_joint_minimum_for_both_median_definitions(n, fraction):
    baseline = [2., 38., 20., 13., 4., 8., 22.][:n]
    candidate = [10., 24., 14., 2., 1., 1., 12.][:n]
    pairs = [(row(a, 1., 1.), row(b, float(i % 3), 0. if i == 2 else 2.)) for i, (a, b) in
             enumerate(zip(baseline, candidate, strict=True))]
    result = repair_budget(pairs, .25, fraction)
    admissible = {i for i, pair in enumerate(pairs) if acceptable_pair(*pair, .25)}
    remaining = set(range(n)) - admissible
    opt = [None, None, None]
    for k in range(len(remaining) + 1):
        for chosen in combinations(remaining, k):
            use = admissible.union(chosen)
            paid = [min(a, b * fraction) if i in use else a for i, (a, b) in
                    enumerate(zip(baseline, candidate, strict=True))]
            summed = fsum(paid) <= fsum(baseline) / 2
            middle = median(x / a for x, a in zip(paid, baseline, strict=True)) <= .5
            for j, ok in enumerate((summed, middle, summed and middle)):
                if ok and opt[j] is None:
                    opt[j] = k
    assert [result["min_repairs_for_sum"], result["min_repairs_for_median"]] == opt[:2]
    if opt[2] is None:
        assert result["joint_lower_bound"] is result["joint_upper_bound"] is None
    else:
        assert result["joint_lower_bound"] <= opt[2] <= result["joint_upper_bound"]
