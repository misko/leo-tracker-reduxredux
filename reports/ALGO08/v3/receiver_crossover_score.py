"""Score completed receiver crossover decisions against the sealed controls."""

import argparse
import csv
import gzip
from hashlib import sha256
import json
from pathlib import Path

from aperture_score import PHYSICAL, SIMULATED, face_clearance_km, references
from aperture_trial import ARMS, read, write
from mixture_score import section
from receiver_crossover import CASES


HERE = Path(__file__).resolve().parent
MEASUREMENTS = HERE / "measurements"


def outcome(result, truth, repaired_arms):
    return dict(
        status=result["status"], reason=result["reason"],
        evidence={key: result.get(key) for key in ("associated", "owners", "objective_replay", "grid_points")},
        **section(result["arms"], truth, repaired_arms),
    )


def compare(candidate, reference, locked, truth):
    if candidate["identity"] != locked["candidate"] or reference["identity"] != locked["v3"]:
        raise ValueError("Solver outputs refer to different saved inputs")
    if not (candidate["repair_enabled"] and reference["repair_enabled"]):
        raise ValueError("Use the same common-support repair in both arms")
    route, = candidate["attempts"]
    original_route, = reference["attempts"]
    repaired_arms = reference["result"]["arms"]
    contained = face_clearance_km(locked["candidate"]["offer"], truth) >= 0
    scored = {name: outcome(result, truth, repaired_arms) for name, result in
              (("candidate", candidate["result"]), ("repaired_v3", reference["result"]),
               ("installed_v3", reference["control"]))}
    deltas = [scored["candidate"]["arms"][arm]["delta_error_km"] for arm in ARMS]
    status = scored["candidate"]["status"]
    valid = status == "ok" and all(d is not None and d <= .25 for d in deltas) if contained else status == "withheld"
    return dict(
        contained=contained, passes=valid and route["decision"] != "fallback",
        candidate_route=route["decision"], candidate_route_reason=route.get("reason"),
        repaired_v3_route=original_route["decision"], candidate_repair=route.get("repair"),
        fallback=route.get("fallback_clocks"), candidate_clocks=candidate["charged"],
        repaired_v3_clocks=reference["charged"], installed_v3_clocks=reference["control_clocks"],
        candidate_roles=candidate["published_roles"], reference_roles=reference["published_roles"],
        **scored,
    )


def density_budget(acquisition, solver, v3):
    detection = acquisition["detection_file_elapsed_s"]
    target = float(v3["elapsed_s"]) / 2
    publication = float(v3["terminal_to_exit_s"])
    projected = detection + solver["elapsed_s"] + publication
    # The complete candidate ran on one pinned core. CPU after the handoff
    # cannot exceed the elapsed time that remained in that process.
    lower_cpu = max(0., acquisition["complete_cpu_s"] - (acquisition["complete_elapsed_s"] - detection))
    return dict(v3_historical_elapsed_s=float(v3["elapsed_s"]),
                v3_historical_acquisition_s=float(v3["launch_to_detections_s"]),
                target_elapsed_s=target, alternate_acquisition_s=detection,
                charge_publication_s=publication, alternate_saved_solver_elapsed_s=solver["elapsed_s"],
                projected_elapsed_s=projected, projected_speedup=float(v3["elapsed_s"]) / projected,
                excess_with_free_solver_elapsed_s=detection + publication - target,
                maximum_acquisition_elapsed_s=target - publication - solver["elapsed_s"],
                alternate_acquisition_cpu_lower_bound_s=lower_cpu,
                alternate_combined_cpu_lower_bound_excluding_publication_s=lower_cpu + solver["cpu_s"],
                v3_historical_half_cpu_s=float(v3["cpu_s"]) / 2)


def score(directory, bindings, summary, full):
    paths = [directory / f"{case}.json" for case in CASES]
    candidates = {case: read(path) for case, path in zip(CASES, paths, strict=True)}
    control = MEASUREMENTS / "blind-joint-repair.json.gz"
    reference = json.loads(gzip.decompress(control.read_bytes()))["receipts"]
    locked = read(bindings)
    truth = references()
    scored = {case: compare(candidates[case], reference[case], locked[case], truth[case]) for case in CASES}
    stage = HERE / "first-55/stage-clocks.csv"
    with stage.open() as stream:
        dense, = [row for row in csv.DictReader(stream) if row["recording"] == "DS30-0008"]
    cost = density_budget(locked["DS30-0008"]["candidate"]["acquisition"],
                          scored["DS30-0008"]["candidate_clocks"], dense)
    pins = {path.name: sha256(path.read_bytes()).hexdigest()
            for path in (*paths, bindings, control, stage, PHYSICAL, SIMULATED)}
    result = dict(cases=scored, dense_elapsed_projection=cost, input_sha256=pins)
    write(summary, result)
    with full.open("xb") as stream:
        stream.write(gzip.compress(json.dumps(dict(result, candidate_receipts=candidates), sort_keys=True,
                                             separators=(",", ":"), allow_nan=False).encode(), mtime=0))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for option in ("directory", "bindings", "summary", "full"):
        parser.add_argument(option, type=Path)
    score(**vars(parser.parse_args()))
