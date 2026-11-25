from fractions import Fraction
import json
from random import Random

import pytest

from reports.ALGO08.v3.ds30_oracle_routing import coverage, meets
from reports.ALGO08.v3.ds30_routing_first64 import (
    CASE_KEY, admissible, certified_route, check_certificate, primary, restricted_json,
)


def row(case, a, b):
    return dict(case=case, c0_error_km=a, fitted_c_error_km=b,
                c0_fix=a is not None, fitted_c_fix=b is not None)


@pytest.mark.parametrize("seed", range(8))
def test_exact_sum_matches_exhaustive_curves_with_missing_fixes_and_ties(seed):
    rng = Random(seed)
    choices = [None, .04, .23, .23, .51, 1.5]
    pairs = [(row(str(i), rng.choice(choices), rng.choice(choices)),
              row(str(i), rng.choice(choices), rng.choice(choices))) for i in range(9)]
    clocks = [(Fraction(rng.randrange(1, 100), 10), Fraction(rng.randrange(1, 100), 100))
              for _ in pairs]
    thresholds = coverage(pairs, None)
    expected = min(sum(times[bool(route & (1 << i))] for i, times in enumerate(clocks))
                   for route in range(1 << len(pairs)) if meets(thresholds, route))
    result = primary(pairs, clocks)
    observed = result["strict"]
    assert observed["lower_total_units"] <= expected*result["clock_unit_denominator"] <= observed["total_units"]
    assert observed["total_units"] == expected*result["clock_unit_denominator"]
    assert meets(thresholds, observed["mask"])


def test_both_arms_must_use_a_single_choice_even_with_cross_recording_compensation():
    pairs = [(row("A", 1., 2.), row("A", 2., 1.)),
             (row("B", 2., 1.), row("B", 1., 2.)),
             (row("C", None, .2), row("C", None, None))]
    result = primary(pairs, [(Fraction(10), Fraction(2))] * 3)
    assert result["strict"]["candidate_cases"] == ["A", "B"]
    assert result["strict"]["total_units"] == 14
    assert result["unconstrained"]["cumulative"]["fitted_c"]["installed_fixes"] == 3
    assert result["unconstrained"]["cumulative"]["fitted_c"]["routed_fixes"] == 2


def test_nonzero_count_constraints_and_exact_infeasibility():
    weights = [10, 2, -3, 0]
    rows = [(0b0100, 0, 1), (0b0010, 0b0001, 0)]
    feasible = [(sum(w for i, w in enumerate(weights) if route & (1 << i)), route)
                for route in range(16) if admissible(rows, route)]
    selected, proof = certified_route(weights, rows)
    explicit = check_certificate(weights, rows, selected, {0: Fraction(3)})
    optimum = max(gain for gain, _ in feasible)
    assert proof["gain"] == proof["upper_gain"] == explicit["gain"] == explicit["upper_gain"] == optimum
    assert (optimum, selected) in feasible
    with pytest.raises(ValueError, match="count inequalities"):
        check_certificate(weights, rows + [(0, 0b0100, 0)], selected, {})
    with pytest.raises(ValueError, match="Invalid dual multiplier"):
        check_certificate(weights, rows, selected, {0: Fraction(-1)})


def test_label_gate_does_not_decode_excluded_payload():
    good = b'{"case":"DS30-0107","ok":true}'
    excluded = b'{"case":"DS30-0218","do_not_read":???}'
    sliced = restricted_json([excluded, good], CASE_KEY, {"DS30-0107"})
    assert [json.loads(row) for row in sliced] == [{"case": "DS30-0107", "ok": True}]
