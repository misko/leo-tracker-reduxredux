"""Compute the end-to-end target for two disjoint optimizations on the frozen 30 DS30 pairs."""

import argparse
from gzip import decompress
from hashlib import sha256
import json
from math import fsum, isfinite
from pathlib import Path
from statistics import median


RECEIPT = Path(__file__).parent / "measurements" / "first30-after-intake.json.gz"
DIGEST = "5d7b3624bca9f1d808cb0bee044fcadb7c4593054da771d8c57dc0dd1456de3c"


def required_reduction(target_met):
    """Find the smallest fraction of a stage to remove that satisfies a monotone timing gate."""
    if target_met(0.):
        return 0.
    if not target_met(1.):
        return None
    lo, hi = 0., 1.
    for _ in range(54):
        mid = (lo + hi) / 2
        if target_met(mid):
            hi = mid
        else:
            lo = mid
    return hi


def targets(clocks, native_speedup):
    """Clock rows are installed total, candidate total, native callbacks, and chosen solver scope."""
    if not clocks or not isfinite(native_speedup) or native_speedup < 1:
        raise ValueError("Expected measured rows and a finite callback speedup of at least one")
    reduced = []
    for installed, current, native, solver in clocks:
        if (not all(isfinite(t) for t in (installed, current, native, solver)) or min(installed, current) <= 0
                or min(native, solver) < 0 or native + solver > current):
            raise ValueError("Expected disjoint stages within a positive recorded runtime")
        reduced.append((installed, current - native * (1 - 1 / native_speedup), solver))
    half_sum = .5 * fsum(a for a, _, _ in reduced)
    summed = required_reduction(lambda f: fsum(b - f * s for _, b, s in reduced) <= half_sum)
    paired = required_reduction(lambda f: median((b - f * s) / a for a, b, s in reduced) <= .5)
    return dict(summed=summed, paired_median=paired,
                both=max(summed, paired) if summed is not None and paired is not None else None)


def first30():
    data = RECEIPT.read_bytes()
    if sha256(data).hexdigest() != DIGEST:
        raise ValueError("Expected the attested first-30 clock partition")
    return json.loads(decompress(data))["cases"]


def design_point(clocks):
    predicted = [b - n * (1 - 1 / 1.5) - s * (1 - 1 / 1.4) for _, b, n, s in clocks]
    baseline = [a for a, *_ in clocks]
    return dict(summed_speedup=fsum(baseline) / fsum(predicted),
                median_paired_speedup=1 / median(t / a for t, a in zip(predicted, baseline, strict=True)),
                excess_over_half_s=fsum(predicted) - .5 * fsum(baseline))


def held_clocks(campaign, *, split_apertures=False):
    from .field_speed_reachability import BUILD, PLAN, STOCK, checked, reconcile

    plan = json.loads(checked(campaign / "plan.json", PLAN))
    order = list(dict.fromkeys([*plan["smoke"], *(r["case"] for r in plan["cases"])]))
    # Relocation moved 0452's completion behind 0124 inside the development group.
    if set(order[:30]) != {c["case"] for c in first30()}:
        raise ValueError("Unexpected development panel")
    enrollment = {r["case"]: r for r in plan["cases"]}
    seal = json.loads((campaign / "rows-with-relocations-seal.json").read_bytes())
    if seal["plan_sha256"] != "sha256:" + PLAN:
        raise ValueError("Different field experiment")
    export = checked(campaign / "rows-with-relocations.jsonl", seal["combined_sha256"])
    records = [json.loads(r) for r in export.splitlines()]
    lookup = {(r["case"], r["algorithm"]): r for r in records}
    if len(lookup) != 910 or len(records) != len(lookup):
        raise ValueError("Expected one row per enrolled arm")
    result = []
    for case in order[30:46]:
        stock, candidate = (lookup[case, role] for role in ("installed", "successor"))
        for row, pin in ((stock, STOCK), (candidate, BUILD)):
            if (row["verified_pair"] is not True or row["acquisition_verified"] is not True
                    or row["build_sha256"] != "sha256:" + pin or row["case_id"] != enrollment[case]["case_id"]
                    or row["manifest_raw_authority_sha256"] != enrollment[case]["manifest_raw_authority_sha256"]
                    or row.get("relocation_proof_sha256") != seal["proofs"].get(case)):
                raise ValueError(f"Incomplete or unbound field recording {case}")
            receipt = (campaign / row["attempt"]).resolve(strict=True)
            if not receipt.is_relative_to(campaign):
                raise ValueError("Result outside the original campaign")
            actual = json.loads(checked(receipt, row["attempt_result_sha256"]))
            if any(row[k] != actual[k] for k in ("elapsed_s", "cpu_s", "outcome", "algorithm")):
                raise ValueError("Export differs from measured process result")
        d = reconcile(campaign, stock, candidate)
        record = dict(case=case, installed_s=d["stock_wall_s"], candidate_s=d["actual_wall_s"],
                      native_s=d["native_detector_s"], solver_s=d["work"]["solver"]["wall_s"],
                      installed_result=stock["attempt_result_sha256"], candidate_pins=d["pins"])
        if split_apertures:
            source = (campaign / candidate["attempt"]).parent / "publication/unified-short-bootstrap.json"
            raw = json.loads(checked(source, d["pins"]["raw"]))
            native = raw["receiver_audit"]["native"]
            record.update(aperture_seconds(native["native_wall_ns"], record["native_s"]))
            record["short_lanes"] = native["native_calls"].get("short_primary", 0)
            record["short_positives"] = native["factors"].get("short_primary", 0)
        result.append(record)
    return result


def aperture_seconds(modes_ns, expected):
    if (not modes_ns.keys() <= {"short_primary", "full"}
            or any(type(v) is not int or v < 0 for v in modes_ns.values())
            or sum(modes_ns.values()) / 1e9 != expected):
        raise ValueError("Aperture clocks must partition measured native time")
    return dict(short_s=modes_ns.get("short_primary", 0) / 1e9, full_s=modes_ns.get("full", 0) / 1e9)


def aperture_targets(rows):
    # Apply a fixed solver and optional full-anchor saving, then solve only for the short callback.
    required = {}
    for full_rate in (1., 1.25, 1.5):
        adjusted = [(a, b - full * (1 - 1 / full_rate), solver, short) for a, b, solver, short, full in rows]
        required[full_rate] = targets(adjusted, 1.4)
    return dict(pairs=len(rows), short_s=fsum(r[3] for r in rows), full_s=fsum(r[4] for r in rows),
                required_short_fraction_removed=required)


def price_apertures(campaign):
    from .field_speed_reachability import checked
    from .first30_after_intake import NATIVE

    receipt = json.loads(decompress(checked(RECEIPT.with_name("first30-empty-call-roof.json.gz"), NATIVE)))
    first = {r["case"]: r for r in first30()}
    development = []
    for r in receipt["cases"]:
        case = first[r["case"]]
        if r["candidate_join_sha256"] != case["pins"]["result"]:
            raise ValueError("Different detector run in the first-30 budget")
        times = aperture_seconds({k: v["elapsed_ns"] for k, v in r["modes"].items()}, case["native_detector_s"])
        development.append((case["stock_wall_s"], case["actual_wall_s"], case["phases"]["outer"]["elapsed_s"]["solve"],
                            times["short_s"], times["full_s"]))
    later = [(r["installed_s"], r["candidate_s"], r["solver_s"], r["short_s"], r["full_s"])
             for r in held_clocks(campaign, split_apertures=True)]
    return {name: aperture_targets(rows) for name, rows in
            (("first30", development), ("next16", later), ("first46", development + later))}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--check-next-16", type=Path, metavar="CAMPAIGN")
    mode.add_argument("--price-apertures", type=Path, metavar="CAMPAIGN")
    args = parser.parse_args()
    if args.price_apertures:
        print(json.dumps(price_apertures(args.price_apertures.resolve(strict=True)), indent=2))
        return
    if args.check_next_16:
        cases = held_clocks(args.check_next_16.resolve(strict=True))
        clocks = [(r["installed_s"], r["candidate_s"], r["native_s"], r["solver_s"]) for r in cases]
        print(json.dumps(dict(cases=cases, design_point=design_point(clocks),
                              required_solver_reduction=targets(clocks, 1.5)), indent=2))
        return
    cases = first30()
    rows = {"whole_solver": [], "accepted_and_rejected_proposals": [], "accepted_proposals": []}
    for c in cases:
        phases = c["phases"]
        solver = phases["solver"]["elapsed_s"]
        base = (c["stock_wall_s"], c["actual_wall_s"], c["native_detector_s"])
        rows["whole_solver"].append((*base, phases["outer"]["elapsed_s"]["solve"]))
        rows["accepted_and_rejected_proposals"].append((*base, solver["accepted_proposal"] + solver["rejected_proposal"]))
        rows["accepted_proposals"].append((*base, solver["accepted_proposal"]))
    output = {name: {speed: targets(v, speed) for speed in (1., 1.25, 1.5, 2., 3.)} for name, v in rows.items()}
    print(json.dumps(dict(measured_pairs=len(cases), input_sha256=DIGEST, required_fraction_removed=output,
                          design_point=design_point(rows["whole_solver"])), indent=2))


if __name__ == "__main__":
    main()
