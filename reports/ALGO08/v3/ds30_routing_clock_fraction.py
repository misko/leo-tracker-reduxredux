"""Certify the largest uniform candidate clock fraction for half summed wall time."""

import argparse
from fractions import Fraction
import gzip
import json
from pathlib import Path
from statistics import median

from .ds30_oracle_routing import checked, coverage, meets
from .ds30_routing_first64 import certified_route, check_certificate, constraints, summary


RECEIPT = "sha256:6958f0a428eeb70ca147aa19c595a834298f1e613ae0776a07e448f230406b10"


def rational(value):
    return [value.numerator, value.denominator]


def weights_at(wall, fraction):
    return [fraction.denominator*installed-fraction.numerator*candidate for installed, candidate in wall]


def candidate_cost(wall, mask):
    return sum(candidate for i, (_, candidate) in enumerate(wall) if mask & (1 << i))


def largest_fraction(wall, rows):
    """Iterate exact ratio improvements and certify the final half-time boundary."""
    if not wall or any(min(pair) <= 0 for pair in wall):
        raise ValueError("Expected a nonempty panel with positive integer clocks")
    baseline = sum(installed for installed, _ in wall)
    fraction = Fraction(0)
    trace = []
    while True:
        mask, certificate = certified_route(weights_at(wall, fraction), rows)
        target = Fraction(baseline*fraction.denominator, 2)
        surplus = Fraction(certificate["gain"])-target
        trace.append(dict(fraction=rational(fraction), mask=mask, certificate=certificate,
                          half_time_surplus_scaled_units=rational(surplus)))
        if surplus < 0:
            raise ValueError("No feasible half-time route was found at the starting fraction")
        if surplus == 0:
            if certificate["upper_gain"] != target:
                raise ValueError("The boundary witness lacks a matching integer dual upper bound")
            # A larger fraction makes every previously feasible positive-cost
            # route slower, while the all-installed route cannot reach half time.
            return fraction, mask, trace
        fraction += surplus/(fraction.denominator*candidate_cost(wall, mask))


def verify_endpoints(wall, rows, previous):
    baseline = sum(installed for installed, _ in wall)
    result = {}
    for value, name, key in ((0, "free_candidate", "free_candidate_certificate"),
                             (1, "strict", "certificate")):
        old = previous[name]
        archive = previous[key]
        multipliers = {i: Fraction(n, d) for i, n, d in archive["multipliers"]}
        proof = check_certificate(weights_at(wall, Fraction(value)), rows, old["mask"], multipliers)
        total = baseline-proof["gain"]
        if (proof["gain"] != archive["gain"] or proof["gain"] != proof["upper_gain"]
                or total != old["total_units"] or total != old["lower_total_units"]
                or (2*total <= baseline) != (value == 0)):
            raise ValueError("The frozen zero/one endpoint does not verify")
        result[str(value)] = dict(mask=old["mask"], total_wall_units=total, half_time_feasible=value == 0,
                                  certificate=proof)
    return result


def solve_receipt(path):
    doc = json.loads(gzip.decompress(checked(path, RECEIPT)))
    rows = doc["measurements"]
    pairs = [(row["installed"] | {"case": row["case"]}, row["successor"] | {"case": row["case"]}) for row in rows]
    if len(rows) != 64 or [r["position"] for r in rows] != list(range(1, 65)):
        raise ValueError("The frozen prefix changed")
    wall = [(a["wall_units"], b["wall_units"]) for a, b in pairs]
    scale = doc["result"]["clock_unit_denominator"]
    groups = coverage(pairs, None)
    inequalities = constraints(groups)
    endpoints = verify_endpoints(wall, inequalities, doc["result"])
    fraction, mask, trace = largest_fraction(wall, inequalities)
    ratios = [fraction*Fraction(candidate, installed) if mask & (1 << i) else Fraction(1)
              for i, (installed, candidate) in enumerate(wall)]
    median_ratio = median(ratios)
    scaled = [(fraction.denominator*a, fraction.numerator*b) for a, b in wall]
    route = summary(pairs, scaled, groups, mask, scale*fraction.denominator)
    if not (0 < fraction < 1 and meets(groups, mask) and 2*route["total_units"] == route["installed_total_units"]):
        raise ValueError("The boundary witness does not meet the frozen problem")
    installed_fallback = sum(a for i, (a, _) in enumerate(wall) if not mask & (1 << i))
    candidate_original = candidate_cost(wall, mask)
    return dict(frozen_receipt_sha256=RECEIPT, frozen_source=doc["source"], pairs=len(pairs),
                count_inequalities=len(inequalities), original_clock_denominator=scale,
                largest_fraction=rational(fraction), largest_fraction_decimal=float(fraction),
                required_reduction=rational(1-fraction), required_reduction_decimal=float(1-fraction),
                candidate_speed_multiplier=float(1/fraction), median_ratio_exact=rational(median_ratio),
                largest_fraction_is_sharp_for_both=median_ratio <= Fraction(1, 2),
                installed_fallback_wall_s=installed_fallback/scale,
                measured_candidate_wall_s=candidate_original/scale,
                scaled_candidate_wall_s=float(fraction*candidate_original/scale),
                installed_choices=len(pairs)-mask.bit_count(), candidate_choices=mask.bit_count(),
                route=route, endpoint_certificates=endpoints, trace=trace)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("frozen_receipt", type=Path)
    args = parser.parse_args()
    print(json.dumps(solve_receipt(args.frozen_receipt), indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
