"""Compare successive fixes from nearby recordings of the same stationary receiver.

Follow the frozen enrollment order. Match each incoming case to the nearest unpaired
earlier enrollee by absolute capture-start separation, up to one hour inclusive.
Break ties by case label. Require distinct physical recordings and an identical
eligible survey reference. Both builds use these same pairs, including failures.
This measures between-scan repeatability without using either build's position to
choose pairs. It does not feed the reference or the previous fix to either solver.
"""

import argparse
import gzip
import json
from pathlib import Path
from statistics import median

from .ds30_stage_progress import verified_measurements
from .full_successor_score import ARMS, BUILDS, MANIFEST, ROOT, checked, distance_km, frozen_stage_order, roster


HOUR_NS = 3_600_000_000_000


def match_neighbors(order, assigned, starts):
    waiting = set()
    matches = []
    for case in order:
        ref = assigned[case]["reference"]
        if ref is None:
            continue
        neighbors = [(abs(starts[case] - starts[other]), other) for other in waiting
                     if assigned[other]["reference"] == ref
                     and assigned[other]["physical_content"] != assigned[case]["physical_content"]]
        if neighbors:
            delta, other = min(neighbors)
            if delta <= HOUR_NS:
                matches.append((other, case, delta / 1e9))
                waiting.remove(other)
                continue
        waiting.add(case)
    return matches


def compare(matches, positions, arm):
    rows = []
    for earlier, later, gap_s in matches:
        separations = {role: distance_km(positions[earlier, role][arm]["latlon"],
                                         positions[later, role][arm]["latlon"]) for role in BUILDS}
        rows.append(dict(first_enrolled=earlier, second_enrolled=later, gap_s=gap_s, **separations))
    common = [r for r in rows if all(r[role] is not None for role in BUILDS)]
    return dict(pairs=len(rows), paired_fixes={role: sum(r[role] is not None for r in rows) for role in BUILDS},
                shared=len(common), median_separation_km={
                    role: median(r[role] for r in common) if common else None for role in BUILDS},
                candidate_more_variable=sum(r["successor"] > r["installed"] for r in common), recordings=rows)


def evaluate(raw, seal, limit=None):
    assigned = roster()
    verified = {a["case"] for a, _ in verified_measurements(raw, seal, assigned)}
    order = frozen_stage_order({case: (r["case_id"], r["physical_content"]) for case, r in assigned.items()})
    prefix = next((i for i, case in enumerate(order) if case not in verified), len(order))
    if limit is None:
        limit = prefix
    if not 0 <= limit <= prefix:
        raise ValueError("Requested cohort exceeds the verified enrollment prefix")
    data = ROOT / "reports/2026_11_20_ds30_fast/dataset/manifest.json.gz"
    source = json.loads(checked(gzip.decompress(data.read_bytes()), MANIFEST))
    starts = {r["dataset_label"]: r["captured_utc_ns"] for r in source["members"]}
    matches = match_neighbors(order[:limit], assigned, starts)
    positions = {(r["case"], r["algorithm"]): r["arms"] for line in raw.splitlines()
                 if (r := json.loads(line))["verified_pair"]}
    return dict(export_sha256=seal["combined_sha256"], prefix=limit, threshold_seconds=HOUR_NS / 1e9,
                calibrations={arm: compare(matches, positions, arm) for arm in ARMS})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("export", type=Path)
    parser.add_argument("--limit", type=int, help="Size of an earlier verified enrollment prefix")
    args = parser.parse_args()
    seal = json.loads(args.export.with_name("rows-with-relocations-seal.json").read_bytes())
    print(json.dumps(evaluate(args.export.read_bytes(), seal, args.limit), indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
