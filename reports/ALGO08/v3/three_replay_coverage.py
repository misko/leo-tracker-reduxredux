"""Price only the three measured frequency corrections in the frozen first 65 pairs."""

import argparse
from fractions import Fraction
import gzip
import json
import math
from pathlib import Path
from statistics import median

from .ds30_oracle_routing import checked, coverage, meets
from .ds30_routing_clock_fraction import largest_fraction
from .ds30_routing_first64 import ARMS, certified_route, constraints
from .full_successor_score import PINS, empirical_accuracy_gap


MEASUREMENTS = Path(__file__).with_name("measurements")
EXPORT = "sha256:3fb2f2999401ce551d8c5fa0b2cebc14caec7246ffcbfd14f387a8f1422cb182"
SOURCES = {
    "ds30-routing-first64.json.gz": "sha256:6958f0a428eeb70ca147aa19c595a834298f1e613ae0776a07e448f230406b10",
    "held-shrink-0019-ram.json": "sha256:eafff4168a352f41f7158acaa492e2e0465217b128860acdbce02d319e7da5e6",
    "held-shrink-0274.json": "sha256:3e631b3ea4ac911cd21cf74fafe19f966706e7f12ca9d1e39e40b5fde2c0488a",
    "masked-cfo-0218-prospective-score.json": "sha256:c41eea3163edd161773a72e03d324ad99a2f77af9a2470d5147f5472b8a34a8b",
}


def substitute(pairs, changes):
    """Use a paired, completed replay only when its control reproduces the field errors."""
    updated = []
    used = set()
    for installed, candidate in pairs:
        case = candidate["case"]
        replacement = candidate.copy()
        if case in changes:
            if case in used or installed["case"] != case:
                raise ValueError("Duplicate or mismatched physical comparison")
            for arm in ARMS:
                key = arm + "_error_km"
                before, after = changes[case][arm]
                if (not candidate[arm + "_fix"] or candidate[key] is None or
                        not math.isclose(1000*candidate[key], before, rel_tol=0, abs_tol=1e-6) or
                        not math.isfinite(after) or after < 0):
                    raise ValueError("Replay does not match the original field fix")
                replacement[key] = after / 1000
            used.add(case)
        updated.append((installed, replacement))
    if used != changes.keys():
        raise ValueError("Expected one field control for every replay")
    return updated


def price(pairs):
    wall = [(a["wall_units"], b["wall_units"]) for a, b in pairs]
    groups = coverage(pairs, None)
    rows = constraints(groups)
    mask, proof = certified_route([a-b for a, b in wall], rows)
    fraction, boundary, trace = largest_fraction(wall, rows)
    if not all(meets(groups, route) for route in (mask, boundary)):
        raise ValueError("An assigned route fails the empirical accuracy target")
    selected = sum(b if mask & (1 << i) else a for i, (a, b) in enumerate(wall))
    paired = median(fraction*b/a if boundary & (1 << i) else Fraction(1) for i, (a, b) in enumerate(wall))
    cover = {}
    for arm in ARMS:
        within = [sum(r[k][arm + "_error_km"] is not None and r[k][arm + "_error_km"] <= 1
                      for r in pairs) for k in (0, 1)]
        cover[arm] = empirical_accuracy_gap(pairs, arm) | dict(within_1km=within)
    return dict(coverage=cover, best_summed_speedup=sum(a for a, _ in wall)/selected,
                best_total_route_mask=mask, total_certificate=proof,
                maximum_candidate_time_fraction=str(fraction), required_cut=1-float(fraction),
                boundary_median_ratio=float(paired), sharp_for_both=paired <= Fraction(1, 2),
                boundary_route_mask=boundary, boundary_certificates=trace)


def run(export):
    def source(name):
        body = checked(MEASUREMENTS/name, SOURCES[name])
        return json.loads(gzip.decompress(body) if name.endswith(".gz") else body)

    first = source("ds30-routing-first64.json.gz")
    records = first["measurements"]
    if ([r["position"] for r in records] != list(range(1, 65)) or
            first["source"]["first_excluded"] != "DS30-0218"):
        raise ValueError("Expected the frozen prefix ending immediately before DS30-0218")
    pairs = [(r["installed"] | {"case":r["case"]}, r["successor"] | {"case":r["case"]}) for r in records]
    old = source("held-shrink-0019-ram.json")["scientific"]
    middle = source("held-shrink-0274.json")
    new = source("masked-cfo-0218-prospective-score.json")
    if not (old["decision"] == "complete" and middle["ordinary_saved"]["exit_code"] ==
            middle["half_blend_saved"]["exit_code"] == 0 and new["exact_ordinary_scientific_parity"] and
            new["corrected_decision"] == "complete"):
        raise ValueError("Expected three verified corrected fixes")
    changes = {"DS30-0019":old["position_error_m"],
               "DS30-0274":{a:[middle[mode]["error_m"][a] for mode in ("ordinary_saved", "half_blend_saved")]
                            for a in ARMS},
               "DS30-0218":{a:[new["arms"][mode][a]["error_m"] for mode in ("ordinary","corrected")] for a in ARMS}}
    last = [json.loads(line, parse_float=str) for line in checked(export, EXPORT).splitlines()
            if b'"case":"DS30-0218"' in line]
    if len(last) != 2 or {r["algorithm"] for r in last} != {"installed", "successor"}:
        raise ValueError("Expected one selected field row per build")
    by_role = {r["algorithm"]:r for r in last}
    extra = []
    scale = first["result"]["clock_unit_denominator"]
    for role, mode in (("installed", "installed"), ("successor", "ordinary")):
        row = by_role[role]
        clock = Fraction(row["elapsed_s"])*scale
        if (not row["verified_pair"] or row["outcome"] != "complete" or row["build_sha256"] != PINS[role] or
                float(row["child_elapsed_s"]) != new["raw_clocks"][role]["elapsed_s"] or clock.denominator != 1):
            raise ValueError("Field clocks or output diverged from the sealed replay input")
        extra.append(dict(case=row["case"], wall_units=int(clock),
                          **{a+"_fix":True for a in ARMS},
                          **{a+"_error_km":new["arms"][mode][a]["error_m"]/1000 for a in ARMS}))
    pairs.append(tuple(extra))
    return dict(field_export=EXPORT, sources=SOURCES, changed_errors_m=changes, pairs=len(pairs),
                measured=price(pairs), three_replacements_at_original_clocks=price(substitute(pairs, changes)))


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("frozen_export", type=Path)
    print(json.dumps(run(cli.parse_args().frozen_export), indent=2, allow_nan=False))
