from fractions import Fraction
from statistics import median

from reports.ALGO08.v3.ds30_oracle_routing import coverage, meets
from reports.ALGO08.v3.ds30_routing_clock_fraction import largest_fraction, verify_endpoints
from reports.ALGO08.v3.ds30_routing_first64 import constraints, primary


def signal(case, a, b):
    return dict(case=case, c0_error_km=a, fitted_c_error_km=b,
                c0_fix=a is not None, fitted_c_fix=b is not None)


def test_integer_ratio_iteration_matches_every_small_route():
    pairs = [(signal("A", 1., 2.), signal("A", 2., 1.)),
             (signal("B", 2., 1.), signal("B", 1., 2.)),
             (signal("C", .5, None), signal("C", .5, None)),
             (signal("D", None, None), signal("D", None, None))]
    wall = [(16, 10), (16, 10), (5, 700), (9, 3)]
    groups = coverage(pairs, None)
    rows = constraints(groups)
    target = Fraction(sum(a for a, _ in wall), 2)
    attainable = []
    for mask in range(1, 1 << len(wall)):
        if meets(groups, mask):
            installed = sum(a for i, (a, _) in enumerate(wall) if not mask & (1 << i))
            candidate = sum(b for i, (_, b) in enumerate(wall) if mask & (1 << i))
            attainable.append(((target-installed)/candidate, mask))

    fraction, mask, trace = largest_fraction(wall, rows)
    assert (fraction, mask) == max(attainable) == (Fraction(18, 23), 0b1011)
    assert trace[0]["mask"] == 0b1111 and len(trace) > 2
    assert trace[-1]["certificate"]["gain"] == trace[-1]["certificate"]["upper_gain"]
    assert trace[-1]["half_time_surplus_scaled_units"] == [0, 1]
    old = primary(pairs, [(Fraction(a), Fraction(b)) for a, b in wall])
    ends = verify_endpoints(wall, rows, old)
    assert ends["0"]["half_time_feasible"] and not ends["1"]["half_time_feasible"]


def test_largest_summed_fraction_does_not_imply_paired_median_pass():
    clocks = [(100, 100), (1, 10), (1, 10)]
    fraction, mask, _ = largest_fraction(clocks, [])
    assert fraction == Fraction(49, 100) and mask == 0b001
    ratios = [fraction*Fraction(b, a) if mask & (1 << i) else Fraction(1)
              for i, (a, b) in enumerate(clocks)]
    assert median(ratios) == 1
