"""Exactly price the two already measured whole-build choices on the frozen DS30 prefix."""

import argparse
from decimal import Decimal
from fractions import Fraction
import gzip
import json
from math import isclose, lcm
from pathlib import Path
import re
from statistics import median

from .ds30_oracle_routing import checked, counts, coverage, digest, frozen_order, meets, optimize
from .full_successor_score import (
    ARMS, BUILDS, REFERENCE, ROOT, VERIFIED, frozen_stage_order, paired_rows,
)


PLAN = "sha256:9deecea6ce5237d01d277370f57b2666f3b84ab96bba72fe0b668c7701d0fc99"
EXPORT = "sha256:139b02f8b016ed6086444fd2d25d8fc062fd246139822f43e13a8c5c3f0be6e7"
SEAL = "sha256:224a79f874bfb2b9fde01a4cc3ed9880f55e4e23a87f6294bafcbf2f898d30dd"
EARLY = "sha256:12e9dad9e2ded14f14ea9d029e73644ab91facf744b434f0d8a5dd9c69912828"
BOUNDARY = "DS30-0218"
LIMIT = 64
CASE_KEY = rb'"case":"(DS30-[0-9]{4})"'
SURVEY_KEY = rb'"dataset_label":"(DS30-[0-9]{4})"'
PLAN_FIELDS = ("assigned_rank", "case_id", "order", "raw_identity_sha256", "manifest_raw_authority_sha256")


def restricted_json(records, key, allowed):
    """Read labels from the canonical envelope, decoding only admitted objects."""
    for raw in records:
        names = re.findall(key, raw)
        if len(names) != 1:
            raise ValueError("Expected one original case label per object")
        if names[0].decode() in allowed:
            yield raw


def source_pairs(plan_path, export_path, seal_path, reference_path):
    plan = json.loads(checked(plan_path, PLAN))
    ordered = frozen_order(plan)
    roster_order = frozen_stage_order({
        entry["case"]: (entry["case_id"], entry["raw_identity_sha256"]) for entry in ordered
    })
    if [entry["case"] for entry in ordered] != roster_order or roster_order[LIMIT] != BOUNDARY:
        raise ValueError("The original pre-0218 enrollment changed")
    selected = {entry["case"]: entry for entry in ordered[:LIMIT]}
    seal = json.loads(checked(seal_path, SEAL))
    if seal["plan_sha256"] != PLAN or seal["combined_sha256"] != EXPORT:
        raise ValueError("The combined seal does not bind the enrolled field plan")

    # This particular canonical reference file uses this first key for every
    # top-level case object. Its sealed bytes are verified before slicing.
    survey = checked(reference_path, "sha256:"+REFERENCE)
    records = survey.split(b'"cases":[', 1)[1].rsplit(b'],"prediction_lock_sha256":', 1)[0]
    surveys = {}
    for record in restricted_json(re.split(rb',(?=\{"acquisition_time_policy":)', records), SURVEY_KEY, selected):
        row = json.loads(record)
        case = row["dataset_label"]
        if case not in selected or case in surveys:
            raise ValueError("Duplicate or unexpected surveyed reference")
        ref = row["reference"] if row["authority_eligible"] else None
        surveys[case] = [ref["latitude_deg"], ref["longitude_deg"]] if ref is not None else None
    if surveys.keys() != selected.keys():
        raise ValueError("The selected prefix lacks its matched reference roster")
    assigned = {
        case: dict(case_id=e["case_id"], raw_authority=e["manifest_raw_authority_sha256"],
                   physical_content=e["raw_identity_sha256"], reference=surveys[case],
                   release_100=e["historical_first100"], recording_state=e["recording_state"])
        for case, e in selected.items()
    }

    rows, elapsed, pins = [], {}, {}
    export = checked(export_path, EXPORT)
    for record in restricted_json(export.splitlines(), CASE_KEY, selected):
        row = json.loads(record)
        case, build = row["case"], row["algorithm"]
        entry = selected[case]
        if (build not in BUILDS or any(row[k] != entry[k] for k in PLAN_FIELDS)
                or row["actual_order"] != entry["order"] or row["first"] != entry["order"][0]
                or row["verified_pair"] is not True or row["acquisition_verified"] is not True
                or row["outcome"] not in VERIFIED
                or row.get("relocation_proof_sha256") != seal["proofs"].get(case)):
            raise ValueError("The selected pair differs from its sealed enrollment and attempt")
        rows.append(row)
        elapsed[case, build] = Fraction(json.loads(record, parse_float=Decimal)["elapsed_s"])
        pins[case, build] = digest(record)
    pairs = paired_rows(rows, assigned)
    clocks = [(elapsed[a["case"], "installed"], elapsed[a["case"], "successor"]) for a, _ in pairs]
    row_hash = {case: {build: pins[case, build] for build in BUILDS} for case in selected}
    inputs = dict(plan_sha256=PLAN, combined_export_sha256=EXPORT, seal_sha256=SEAL,
                  ordinary_ledger_sha256=seal["ledger_snapshot_sha256"],
                  relevant_relocation_sha256={k: v for k, v in seal["proofs"].items() if k in selected},
                  reference_sha256="sha256:"+REFERENCE, enrolled_cases_sha256=digest(
                      ("\n".join(selected)+"\n").encode()), first_excluded=BOUNDARY)
    return pairs, clocks, row_hash, inputs


def constraints(groups):
    """Build one exact integer count inequality per distinct signed change in coverage."""
    return sorted({(candidate & ~base, base & ~candidate, 0) for group in groups.values()
                   for _, base, candidate in group if base & ~candidate})


def admissible(rows, route):
    return all((plus & route).bit_count() - (minus & route).bit_count() >= minimum
               for plus, minus, minimum in rows)


def rational_solution(equations, columns):
    """Reconstruct the reported active dual constraints from their exact coefficients."""
    work = [[Fraction(value) for value in row] for row in equations]
    for i in range(columns):
        pivot = next((j for j in range(i, len(work)) if work[j][i]), None)
        if pivot is None:
            return None
        work[i], work[pivot] = work[pivot], work[i]
        work[i] = [value/work[i][i] for value in work[i]]
        for j, row in enumerate(work):
            if i != j and row[i]:
                work[j] = [left-row[i]*right for left, right in zip(row, work[i], strict=True)]
    if any(row[-1] for row in work[columns:]):
        return None
    return [row[-1] for row in work[:columns]]


def check_certificate(weights, rows, route, multipliers):
    """Verify a feasible route and upper bound in exact arithmetic."""
    if not admissible(rows, route) or route < 0 or route >> len(weights):
        raise ValueError("The proposed route fails the original count inequalities")
    adjusted = list(weights)
    shift = 0
    for index, multiplier in multipliers.items():
        if multiplier < 0 or not 0 <= index < len(rows):
            raise ValueError("Invalid dual multiplier")
        plus, minus, minimum = rows[index]
        shift += minimum*multiplier
        for i in range(len(weights)):
            adjusted[i] += (((plus >> i) & 1) - ((minus >> i) & 1))*multiplier
    gain = sum(weight for i, weight in enumerate(weights) if route & (1 << i))
    upper = Fraction(sum(max(0, value) for value in adjusted)-shift)
    if gain > upper:
        raise ValueError("Primal score exceeds its certified upper bound")
    return dict(gain=gain, upper_gain=upper.numerator//upper.denominator,
                upper_gain_rational=(upper.numerator, upper.denominator),
                multipliers=[(i, value.numerator, value.denominator) for i, value in multipliers.items()])


def certified_route(weights, rows):
    """Use an LP to propose a witness and multipliers, then certify without its float objectives."""
    if not rows:
        route = sum(1 << i for i, weight in enumerate(weights) if weight > 0)
        return route, check_certificate(weights, rows, route, {})

    import numpy as np
    from scipy.optimize import Bounds, LinearConstraint, linprog, milp

    coefficients = [[((plus >> i) & 1)-((minus >> i) & 1) for i in range(len(weights))]
                    for plus, minus, _ in rows]
    minima = np.array([minimum for _, _, minimum in rows])
    matrix = np.array(coefficients)
    scale = max(1, max(abs(weight) for weight in weights))
    objective = -np.array([weight/scale for weight in weights])
    lp = linprog(objective, A_ub=-matrix, b_ub=-minima, bounds=(0, 1), method="highs")
    if not lp.success:
        raise ValueError("The proposal relaxation did not finish")
    if any(not isclose(value, round(value), abs_tol=1e-8) for value in lp.x):
        proposed = milp(objective, integrality=np.ones(len(weights)), bounds=Bounds(0., 1.),
                        constraints=LinearConstraint(matrix, minima, np.inf))
        if not proposed.success:
            raise ValueError("The integer witness proposal did not finish")
    else:
        proposed = lp
    route = sum(1 << i for i, value in enumerate(proposed.x) if round(value))
    approximate = {j: Fraction(round(-dual*scale)) for j, dual in enumerate(lp.ineqlin.marginals) if dual < 0}
    support = list(approximate)
    residuals = [weight+sum(coefficients[j][i]*approximate[j] for j in support)
                 for i, weight in enumerate(weights)]
    equations = [[*(coefficients[j][i] for j in support), -weight]
                 for i, weight in enumerate(weights) if abs(residuals[i]) <= scale/10**10]
    reconstructed = rational_solution(equations, len(support))
    certificate = check_certificate(weights, rows, route, approximate)
    if reconstructed is not None and all(value >= 0 for value in reconstructed):
        exact = check_certificate(weights, rows, route, dict(zip(support, reconstructed, strict=True)))
        if Fraction(*exact["upper_gain_rational"]) <= Fraction(*certificate["upper_gain_rational"]):
            certificate = exact
    return route, certificate


def integer_clocks(clocks):
    denominator = lcm(*(v.denominator for pair in clocks for v in pair))
    return denominator, [tuple(int(value*denominator) for value in pair) for pair in clocks]


def summary(pairs, clocks, groups, route, scale):
    baseline = sum(a for a, _ in clocks)
    times = [pair[bool(route & (1 << i))] for i, pair in enumerate(clocks)]
    total = sum(times)
    selected = [i for i, _ in enumerate(pairs) if route & (1 << i)]
    cumulative = {}
    for arm, comparisons in groups.items():
        _, fixes, routed_fixes = counts(comparisons[0], route)
        shortfalls = [(threshold, named-actual) for threshold, named, actual in
                      (counts(row, route) for row in comparisons[1:]) if actual < named]
        deficit = max((missing for _, missing in shortfalls), default=0)
        cumulative[arm] = dict(
            installed_fixes=fixes, routed_fixes=routed_fixes, finite_thresholds=len(comparisons)-1,
            thresholds_below_installed=len(shortfalls), max_finite_deficit=deficit,
            first_worst_cutoff_km=next((cutoff for cutoff, missing in shortfalls if missing == deficit), None))
    mid = median(Fraction(time, baseline) for time, (baseline, _) in zip(times, clocks, strict=True))
    half = sum(2*time <= baseline for time, (baseline, _) in zip(times, clocks, strict=True))
    return dict(mask=route, candidate_cases=[pairs[i][0]["case"] for i in selected],
                installed_total_units=baseline, total_units=total, total_s=total/scale,
                summed_speedup=baseline/total if total else None,
                seconds_above_half_time=(2*total-baseline)/(2*scale),
                at_or_below_half_time=half, median_paired_wall_ratio=float(mid), cumulative=cumulative)


def primary(pairs, clocks):
    scale, units = integer_clocks(clocks)
    groups = coverage(pairs, None)
    rows = constraints(groups)
    weights = [a-b for a, b in units]
    route, certificate = certified_route(weights, rows)
    if not meets(groups, route):
        raise ValueError("The installed route always certifies feasibility")
    strict = summary(pairs, units, groups, route, scale)
    if strict["installed_total_units"]-certificate["gain"] != strict["total_units"]:
        raise ValueError("Witness elapsed total disagrees with the certified integer objective")
    strict["lower_total_units"] = strict["installed_total_units"]-certificate["upper_gain"]
    all_candidates = (1 << len(units))-1
    free_route, free_certificate = certified_route([a for a, _ in units], rows)
    free = summary(pairs, [(a, 0) for a, _ in units], groups, free_route, scale)
    free["lower_total_units"] = free["installed_total_units"]-free_certificate["upper_gain"]
    return dict(clock_unit_denominator=scale, strict=strict, count_inequalities=len(rows), certificate=certificate,
                installed=summary(pairs, units, groups, 0, scale),
                candidate=summary(pairs, units, groups, all_candidates, scale),
                unconstrained=summary(pairs, units, groups, sum(1 << i for i, w in enumerate(weights) if w > 0), scale),
                free_candidate=free, free_candidate_certificate=free_certificate)


def regression(pairs, clocks, path):
    raw = gzip.decompress(path.read_bytes())
    if digest(raw) != EARLY:
        raise ValueError("The archived exhaustive first-11 result changed")
    historical = json.loads(raw)
    registered = [(row["installed"], row["successor"]) for row in historical["measurements"]]
    for pair, expected in zip(pairs, registered, strict=True):
        if any({k: row[k] for k in old} != old for row, old in zip(pair, expected, strict=True)):
            raise ValueError("The frozen first-11 input scores or clocks differ from the original receipt")
    fresh = optimize(pairs)["strict"]["minimum_sum"]
    archived = historical["result"]["strict"]["minimum_sum"]
    scale, units = integer_clocks(clocks)
    groups = coverage(pairs, None)
    route = min((mask for mask in range(1 << len(pairs)) if meets(groups, mask)),
                key=lambda mask: sum(pair[bool(mask & 1 << i)] for i, pair in enumerate(units)))
    got = summary(pairs, units, groups, route, scale)
    if (fresh["mask"] != archived["mask"] or got["mask"] != archived["mask"]
            or not isclose(got["total_s"], archived["wall"]["total_s"], rel_tol=0., abs_tol=1e-10)):
        raise ValueError("The exact solver did not reproduce the archived exhaustive optimum")
    return dict(input_receipt_sha256=EARLY, compared_routes=1 << len(pairs), strict=got)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--export", type=Path, required=True)
    parser.add_argument("--seal", type=Path, required=True)
    args = parser.parse_args()
    pairs, clocks, row_hashes, source = source_pairs(
        args.plan, args.export, args.seal, ROOT/"reports/2026_11_21_ds30_full/reference-audit.json")
    result = primary(pairs, clocks)
    _, units = integer_clocks(clocks)
    fields = ("algorithm", "outcome", "elapsed_s", "cpu_s", "attempt_result_sha256", "terminal_sha256",
              "authority_sha256", "raw_authority_sha256", "physical_content_sha256", "relocation_proof_sha256",
              "build_sha256", "first", "same_lease", "generation", "timing_scope",
              "c0_fix", "fitted_c_fix", "c0_error_km", "fitted_c_error_km")
    measurements = [
        dict(position=i+1, case=pair[0]["case"],
             **{name: {k: row[k] for k in fields} | dict(wall_units=units[i][role],
                                                        export_line_sha256=row_hashes[row["case"]][name])
                for role, (name, row) in enumerate(zip(BUILDS, pair, strict=True))})
        for i, pair in enumerate(pairs)
    ]
    old = regression(pairs[:11], clocks[:11],
                     ROOT/"reports/ALGO08/v3/measurements/ds30-oracle-routing.json.gz")
    print(json.dumps(dict(source=source, pairs=len(pairs), result=result, first11_regression=old,
                          measurements=measurements), indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
