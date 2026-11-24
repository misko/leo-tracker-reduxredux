"""Read the sealed DS30 pair export and score completed field stages without running either build."""

import argparse
from collections import defaultdict
from hashlib import sha256
import json
from math import fsum
from pathlib import Path

from .full_successor_score import (BUILDS, capture_pace, field_stage_history, frozen_stage_order,
                                  half_time_outcomes, paired_rows, roster)


PLAN = "sha256:9deecea6ce5237d01d277370f57b2666f3b84ab96bba72fe0b668c7701d0fc99"
RELOCATED = {f"DS30-{n:04d}" for n in range(447, 456)}


def verified_measurements(raw, seal, assigned):
    if seal["plan_sha256"] != PLAN or seal["combined_sha256"] != "sha256:" + sha256(raw).hexdigest():
        raise ValueError("Export and seal must agree with the enrolled campaign")
    proofs = seal["proofs"]
    if not proofs.keys() <= RELOCATED or set(seal["pending_relocation_cases"]) != RELOCATED - proofs.keys():
        raise ValueError("Invalid relocation proof roster")
    roles = defaultdict(dict)
    for line in raw.splitlines():
        row = json.loads(line)
        case, role = row["case"], row["algorithm"]
        if case not in assigned or role not in BUILDS or role in roles[case]:
            raise ValueError("Duplicate or unenrolled field arm")
        if row.get("relocation_proof_sha256") != proofs.get(case):
            raise ValueError("Export row differs from its relocation seal")
        roles[case][role] = row
    if roles.keys() != assigned.keys() or any(set(group) != set(BUILDS) for group in roles.values()):
        raise ValueError("Expected both arms for every enrolled recording")
    selected, seen = [], {}
    for case, group in roles.items():
        flags = [r["verified_pair"] for r in group.values()]
        if not all(type(flag) is bool for flag in flags) or flags[0] != flags[1]:
            raise ValueError("Both arms must identify the same verified pair")
        if flags[0]:
            if case in RELOCATED and case not in proofs:
                raise ValueError("A relocated pair needs a verified relocation proof")
            seen[case] = assigned[case]
            selected.extend(group.values())
    return paired_rows(selected, seen)


def progress(raw, seal):
    assigned = roster()
    order = frozen_stage_order({k: (r["case_id"], r["physical_content"]) for k, r in assigned.items()})
    pairs = verified_measurements(raw, seal, assigned)
    history = field_stage_history(pairs, order)
    half_time = sum(2 * b["elapsed_s"] <= a["elapsed_s"] for a, b in pairs)
    # Full DS30 has 455 recordings, so its middle order statistic is the 228th.
    signed_excess = fsum(b["elapsed_s"] - .5 * a["elapsed_s"] for a, b in pairs)
    return dict(export_sha256=seal["combined_sha256"], assigned=len(assigned), verified=len(pairs),
                remaining=len(assigned) - len(pairs), observed_pairs_at_half_time=half_time,
                additional_pairs_needed_for_median=max(0, len(assigned) // 2 + 1 - half_time),
                observed_candidate_wall_minus_half_baseline_s=signed_excess,
                per_recording_half_time_outcomes=half_time_outcomes(pairs),
                runtime_relative_to_observing_span=capture_pace(pairs, assigned), **history)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("export", type=Path, help="Combined rows-with-relocations.jsonl export")
    parser.add_argument("--seal", type=Path, help="Defaults to rows-with-relocations-seal.json beside the export")
    args = parser.parse_args()
    seal = args.seal or args.export.with_name("rows-with-relocations-seal.json")
    print(json.dumps(progress(args.export.read_bytes(), json.loads(seal.read_bytes())), indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
