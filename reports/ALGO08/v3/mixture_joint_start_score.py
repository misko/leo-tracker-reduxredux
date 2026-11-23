"""Compare the two saved-detector solver routes after revealing references."""

import argparse
from hashlib import sha256
import json
from pathlib import Path

from aperture_score import PHYSICAL, SIMULATED, distance_km, face_clearance_km, references
from aperture_trial import ARMS, CASES, read
from mixture_score import BUDGET_CPU_S, section


def ownership(before, after):
    common = before.keys() & after.keys()
    return dict(shared=len(common), changed=sum(before[key] != after[key] for key in common),
                dropped=len(before.keys() - after.keys()), added=len(after.keys() - before.keys()))


def stage(run, row, truth, control):
    cold = row.get("cold", {})
    repair = row.get("repair", {})
    diagnostic = repair.get("finish") or row.get("finish", {})
    point = cold.get("proposed_latlon")
    exact_seed = cold.get("latlon")
    return dict(
        decision=row["decision"], reason=row.get("reason"),
        total=run["charged"],
        stage_clocks={key: value for key, value in row.items() if key.endswith("_clocks")},
        cold_detail={key: value for key, value in cold.items() if key.endswith("_clocks")},
        raw_proposal_error_km=None if point is None else distance_km(point, truth),
        raw_proposal_sampled_rms_hz=cold.get("proposed_sample_rms_hz"),
        full_data_refined_cold_error_km=None if exact_seed is None else distance_km(exact_seed, truth),
        full_data_refined_cold_rms_hz=cold.get("refined_rms_hz"),
        support={key: row["support"].get(key) for key in (
            "full_curved", "initial_curved", "curved_restored", "rechecked_curved", "predictive_points",
        )} if "support" in row else {},
        bounded_repair={key: repair.get(key) for key in ("status", "rejection_counts", "reason")} if repair else {},
        diagnostic=section(diagnostic, truth, control),
        checked_terminal=section(run["result"]["arms"], truth, control),
        fallback_routes=[{key: inner.get(key) for key in ("decision", "reason", "standard_evidence_clocks",
                                                          "fallback_clocks")}
                         for inner in run["repaired_fallback_attempts"]],
        result=run["result"], owner_roles=run["owner_roles"],
    )


def compare(base, candidate, truth):
    if (base["identity"] != candidate["identity"] or base["machine"] != candidate["machine"]
            or base["source_sha256"] != candidate["source_sha256"]
            or base["candidate"] or not candidate["candidate"]):
        raise ValueError("Expected the same input, code and worker settings in both solver modes")
    original, = base["attempts"]
    replacement, = candidate["attempts"]
    baseline = base["result"]["arms"]
    before = stage(base, original, truth, baseline)
    after = stage(candidate, replacement, truth, baseline)
    clearance = face_clearance_km(base["identity"]["offer"], truth)
    if clearance >= 0:
        accepted = replacement["decision"] == "complete" and all(
            arm["delta_error_km"] is not None and arm["delta_error_km"] <= .25
            for arm in after["checked_terminal"]["arms"].values()
        )
    else:
        accepted = replacement["decision"] == "withheld"
    return dict(identity=base["identity"], machine=base["machine"],
                source_sha256=base["source_sha256"], truth_clearance_km=clearance,
                dense_cost_pass=candidate["charged"]["cpu_s"] <= BUDGET_CPU_S if
                base["identity"]["case"] == "DS30-0008" else None,
                quality_pass=accepted, control=before, candidate=after,
                ownership={arm: ownership(base["owners"].get(arm, {}), candidate["owners"].get(arm, {}))
                           for arm in ARMS})


def score(comparisons, output):
    reference = references()
    result = dict(dense_target_cpu_s=BUDGET_CPU_S, cases={},
                  scoring_sha256={path.name: sha256(path.read_bytes()).hexdigest()
                                  for path in (PHYSICAL, SIMULATED)})
    for case, before, after in comparisons:
        if case not in CASES or case in result["cases"]:
            raise ValueError(f"Unexpected or repeated saved offer: {case}")
        control, candidate = read(Path(before)), read(Path(after))
        if control["identity"]["case"] != case:
            raise ValueError("Comparison name differs from the measured offer")
        item = compare(control, candidate, reference[case])
        item["raw_receipt_sha256"] = {name: sha256(Path(path).read_bytes()).hexdigest()
                                     for name, path in (("control", before), ("candidate", after))}
        result["cases"][case] = item
    with output.open("x") as stream:
        print(json.dumps(result, sort_keys=True, indent=2, allow_nan=False), file=stream)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    parser.add_argument("--comparison", dest="comparisons", nargs=3, action="append", required=True,
                        metavar=("CASE", "CONTROL", "CANDIDATE"))
    score(**vars(parser.parse_args()))
