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


def maximize_integer(weights, rows):
    """Find an exact maximizing route using capacity propagation and integer bounds."""
    universe = (1 << len(weights))-1
    beneficial = sum(1 << i for i, weight in enumerate(weights) if weight > 0)
    priority = [1 << i for i in sorted(range(len(weights)), key=lambda i: -abs(weights[i]))]
    nodes = dict(visited=0, infeasible=0, objective_pruned=0, attained_relaxation=0)

    def value(mask):
        score = 0
        while mask:
            bit = mask & -mask
            score += weights[bit.bit_length()-1]
            mask ^= bit
        return score

    best, winner = (0, 0) if admissible(rows, 0) else (None, None)

    def visit(selected, skipped):
        nonlocal best, winner
        nodes["visited"] += 1
        while True:
            more_selected, more_skipped = selected, skipped
            for plus, minus, minimum in rows:
                capacity = (plus & ~skipped).bit_count() - (minus & selected).bit_count()
                if capacity < minimum:
                    nodes["infeasible"] += 1
                    return
                if capacity == minimum:
                    more_selected |= plus & ~skipped
                    more_skipped |= minus & ~selected
            if more_selected & more_skipped:
                nodes["infeasible"] += 1
                return
            if (more_selected, more_skipped) == (selected, skipped):
                break
            selected, skipped = more_selected, more_skipped
        free = universe & ~(selected | skipped)
        greedy = selected | (free & beneficial)
        gain = value(greedy)
        if best is not None and gain <= best:
            nodes["objective_pruned"] += 1
            return
        blocked = []
        for plus, minus, minimum in rows:
            if (plus & greedy).bit_count() - (minus & greedy).bit_count() < minimum:
                flips = free & ((plus & ~greedy) | (minus & greedy))
                blocked.append(flips)
        if not blocked:
            best, winner = gain, greedy
            nodes["attained_relaxation"] += 1
            return
        flips = min(blocked, key=int.bit_count)
        bit = next(bit for bit in priority if flips & bit)
        if greedy & bit:
            visit(selected, skipped | bit)
            visit(selected | bit, skipped)
        else:
            visit(selected | bit, skipped)
            visit(selected, skipped | bit)

    visit(0, 0)
    if winner is not None and (not admissible(rows, winner) or value(winner) != best):
        raise ValueError("The maximizing integer witness failed its original inequalities")
    return winner, best, nodes


def integer_clocks(clocks):
    denominator = lcm(*(v.denominator for pair in clocks for v in pair))
    return denominator, [tuple(int(value*denominator) for value in pair) for pair in clocks]


def summary(pairs, clocks, groups, route, scale):
    baseline = sum(a for a, _ in clocks)
    total = sum(pair[bool(route & (1 << i))] for i, pair in enumerate(clocks))
    selected = [i for i, _ in enumerate(pairs) if route & (1 << i)]
    cumulative = {}
    for arm, comparisons in groups.items():
        _, fixes, routed_fixes = counts(comparisons[0], route)
        cumulative[arm] = dict(
            installed_fixes=fixes, routed_fixes=routed_fixes, finite_thresholds=len(comparisons)-1,
            thresholds_below_installed=sum(actual < named for _, named, actual in
                                           (counts(row, route) for row in comparisons[1:])),
            max_deficit=max(0, max(named-actual for _, named, actual in
                                  (counts(row, route) for row in comparisons))))
    mid = median(Fraction(pair[bool(route & (1 << i))], pair[0]) for i, pair in enumerate(clocks))
    return dict(mask=route, candidate_cases=[pairs[i][0]["case"] for i in selected],
                installed_total_units=baseline, total_units=total, total_s=total/scale,
                summed_speedup=baseline/total if total else None,
                seconds_above_half_time=(2*total-baseline)/(2*scale),
                median_paired_wall_ratio=float(mid), cumulative=cumulative)


def primary(pairs, clocks):
    scale, units = integer_clocks(clocks)
    groups = coverage(pairs, None)
    rows = constraints(groups)
    weights = [a-b for a, b in units]
    route, gain, nodes = maximize_integer(weights, rows)
    if route is None or not meets(groups, route):
        raise ValueError("The installed route always certifies feasibility")
    strict = summary(pairs, units, groups, route, scale)
    if strict["installed_total_units"]-gain != strict["total_units"]:
        raise ValueError("Witness elapsed total disagrees with the certified integer objective")
    all_candidates = (1 << len(units))-1
    free_route, _, free_nodes = maximize_integer([a for a, _ in units], rows)
    return dict(clock_unit_denominator=scale, strict=strict, count_inequalities=len(rows), search=nodes,
                installed=summary(pairs, units, groups, 0, scale),
                candidate=summary(pairs, units, groups, all_candidates, scale),
                unconstrained=summary(pairs, units, groups, sum(1 << i for i, w in enumerate(weights) if w > 0), scale),
                free_candidate=summary(pairs, [(a, 0) for a, _ in units], groups, free_route, scale),
                free_candidate_search=free_nodes)


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
    got = primary(pairs, clocks)["strict"]
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
              "authority_sha256", "timing_scope", "c0_fix", "fitted_c_fix", "c0_error_km", "fitted_c_error_km")
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
