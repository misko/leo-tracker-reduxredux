from math import fsum
from random import Random

import pytest

from reports.ALGO08.v3.ds30_oracle_routing import coverage, meets
from reports.ALGO08.v3.ds30_routing_ceiling import fastest_route, timing_requirement


@pytest.mark.parametrize("cutoffs", [None, [1, 2]])
@pytest.mark.parametrize("fraction", [0., .5, .8, 1.])
def test_matches_enumeration_with_ties_missing_fixes_and_disagreeing_calibrations(cutoffs, fraction):
    rng = Random(502)
    def arm(case):
        errors = [rng.choice([.3, .4, 1., 2.5, None]) for _ in range(2)]
        return dict(case=case, elapsed_s=rng.uniform(1., 3.),
                    **{arm + "_error_km": err for arm, err in zip(("c0", "fitted_c"), errors)},
                    **{arm + "_fix": err is not None for arm, err in zip(("c0", "fitted_c"), errors)})
    pairs = [(arm(str(i)), arm(str(i))) for i in range(9)]
    groups = coverage(pairs, cutoffs)
    expected = min(fsum(fraction*b["elapsed_s"] if mask & (1 << i) else a["elapsed_s"]
                        for i, (a, b) in enumerate(pairs))
                   for mask in range(2**len(pairs)) if meets(groups, mask))
    got = fastest_route(pairs, fraction, cutoffs)
    assert got["optimum_total_s"] == pytest.approx(expected)
    assert got["dual_bound_s"] == pytest.approx(expected)


def test_equal_outputs_permit_independent_fastest_choices():
    def arm(t):
        return dict(case="sample", elapsed_s=t, fitted_c_fix=False, c0_fix=False,
                    c0_error_km=None, fitted_c_error_km=None)
    assert fastest_route([(arm(8), arm(4))])["within_half_total"]
    assert fastest_route([(arm(1), arm(4))])["candidate_choices"] == 0
    borderline = timing_requirement([(arm(8), arm(5))])
    assert borderline["feasible_fraction"] <= .8 < borderline["infeasible_fraction"]
    assert borderline["infeasible_fraction"] - borderline["feasible_fraction"] < .0001
    assert timing_requirement([(arm(8), arm(4))])["feasible_fraction"] == 1.
    fixed = {**arm(8), "c0_fix": True, "c0_error_km": .001}
    assert timing_requirement([(fixed, arm(4))])["feasible_fraction"] is None
