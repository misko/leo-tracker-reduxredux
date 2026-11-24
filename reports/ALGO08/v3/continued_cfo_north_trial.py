"""Verify one continued guarded North raw publication against frozen controls."""

import argparse
from hashlib import sha256
import json
from pathlib import Path
import sys


HERE = Path(__file__).resolve().parent
if __name__ == "__main__":
    sys.path.insert(0, str(HERE))

from aperture_trial import read, write
from empty_bootstrap import checked
from joint_held_north_raw import (ARM_NAMES, PACK_SHA, REFERENCE_PINS, check_arms, check_handoff,
                                 check_selector, compare_figure, launch, references)
from north_held_anchor_pair import publication_evidence, require_resident
from raw_cfo_north_trial import native_file


GUARDED = Path("/dev/shm/leo-v3-joint-held-north-result01")
GUARDED_PINS = {
    "binding": "9cfe37bcd5af105fbff5fd49ba3fec703c52516a323227f79e670bc5b473a958",
    "sealed": "dd36d98a63a2d3208aa513bfe52a7984095a4ea8ce5fd44d0adca9415ad47cbc",
    "score": "36c6ef63d23e4f91670980b9e995b5b659b8e2b7f866810cf3d0b810e7275a21",
}


def control():
    binding, result = (json.loads(checked(GUARDED / f"{key}.json", GUARDED_PINS[key]))
                       for key in ("binding", "sealed"))
    clock = result["clock"]
    if (binding["pack_sha256"] != PACK_SHA or result["binding_sha256"] != GUARDED_PINS["binding"]
            or binding["historical"] != REFERENCE_PINS or not clock["elapsed_s"] > 0
            or any(clock[k] for k in ("exit_code", "major_faults", "input_blocks"))):
        raise ValueError("The all-paid control must use the original resident guarded route")
    for state in result["cache"].values():
        for census in state.values():
            require_resident(census)
    return binding, result


def compare_rows(actual, previous):
    from held_cycle_refined import CFO
    from leo.contracts.digests import canonical_digest

    def opportunity(row):
        return {name: value for name, value in row.items() if name != "candidates"}

    differences = []
    max_delta = 0.0
    for row, old in zip(actual, previous, strict=True):
        if opportunity(row) != opportunity(old):
            raise ValueError("The signed chronological opportunity changed")
        if row["candidates"] != old["candidates"]:
            differences.append((row["visit_index"], row["receiver_id"]))
            if len(row["candidates"]) == len(old["candidates"]) == 1:
                max_delta = max(max_delta, abs(row["candidates"][0][CFO] - old["candidates"][0][CFO]))
    return dict(checked_probes=len(actual), changed_lanes=len(differences), first_changes=differences[:8],
                max_changed_cfo_hz=max_delta, signed_probe_sha256=canonical_digest(actual))


def seal(root, *, verified_source=None, allow_resident_process_paging=False):
    from anchor_exposure import enroll
    from leo.contracts.digests import canonical_digest
    from leo.storage.fast_standard_analysis import FastStandardAnalysisStore

    old_binding, old = control()
    _, controls = references()
    stock = controls["stock"]
    binding, clock = (read(root / f"{key}.json") for key in ("binding", "clock"))
    for name, pin in binding["source_sha256"].items():
        if verified_source is None:
            checked(HERE / name, pin)
        else:
            verified_source(name, pin)
    matched = ("request", "assignment", "historical", "machine", "selector", "libraries", "pack_sha256")
    if (any(binding[k] != old_binding[k] for k in matched) or clock["exit_code"]
            or not allow_resident_process_paging and any(clock[k] for k in ("major_faults", "input_blocks"))):
        raise ValueError("Pair does not match the original resident assignment and native libraries")
    cache = {when: read(root / f"cache-{when}.json") for when in ("before", "after")}
    for state in cache.values():
        for census in state.values():
            require_resident(census)
    output = root / "containing"
    bootstrap, research = (read(output / f"{key}.json") for key in
                           ("unified-short-bootstrap", "joint-research-receipt"))
    selection_file = root / "containing-held-cycle-refined.json"
    selection = read(selection_file)
    request, receipt = binding["request"], bootstrap["receipt"]
    candidate = publication_evidence(output, receipt, clock, binding["assignment"])
    native = candidate.pop("native")
    check_handoff(bootstrap, research, native, candidate, request)
    check_selector(bootstrap, selection, native, request)
    check_arms(candidate["verified"]["arms"])
    packet = native_file(output)
    if (selection_file.stat().st_mtime_ns > packet.stat().st_mtime_ns
            or not candidate["detector_ready_s"] <= candidate["verified"]["terminal_file_s"]
            <= candidate["report_ready_s"] <= clock["elapsed_s"]):
        raise ValueError("Route, handoff and publication must seal in the measured order")

    receiver = dict(bootstrap["receiver_recipe"])
    continued = receiver.pop("continued_cfo")
    if (continued["wrapper_sha256"] != binding["source_sha256"]["continued_cfo.py"]
            or receiver != old["raw"]["receiver_recipe"]):
        raise ValueError("Only the signed continuation wrapper may change the receiver recipe")
    old_native = json.loads(checked(Path(old["packet"]), old["candidate"]["native_sha256"][7:]))
    factors = compare_rows(native["source"]["probes"], old_native["source"]["probes"])
    old_selection = old["raw"]["held_anchor_route"]
    old_verified = old["candidate"]["verified"]
    verified = candidate["verified"]
    store = FastStandardAnalysisStore(output)
    grid, path = store.position_grid(receipt["run_id"]), store.position_path(receipt["run_id"])
    if (not grid["matched_c_grid"] or grid["planned_points"] != len(grid["points"])
            or grid["evaluated_points"] != len(grid["points"]) or not path["stages"]):
        raise ValueError("Expected complete matched calibration grid and position path")
    roles = {arm: research["selected_rows"][arm] for arm in ARM_NAMES}
    for arm, rows in roles.items():
        owners = {identifier: satellite for identifier, satellite, _ in rows}
        if not owners or len(owners) != len(rows) or canonical_digest(owners) != verified["owners"][arm]:
            raise ValueError("Selected roles do not bind the verified terminal owners")
    plots = {name: compare_figure(image, old["candidate"]["figures"][name])
             for name, image in candidate["figures"].items()}
    native_counts = bootstrap["receiver_audit"]["native"]
    old_counts = old["raw"]["receiver_audit"]["native"]
    finish = research["route_details"]["named_survivor_fit"]
    retained_short = sum(event[-1][1] for event in enroll(native) if event[4] == "short")
    parity = dict(original_history=selection["choice"]["route"] == "history" and all(
        selection[key] == old_selection[key] for key in ("choice", "measured", "selected", "pre_refinement_probes_sha256")),
        factors=factors["changed_lanes"] == 0,
        opportunities=(candidate["opportunity_sha256"] == old["candidate"]["opportunity_sha256"]
                       == stock["opportunity_sha256"]),
        native_primary=native_counts["native_calls"] == old_counts["native_calls"] and
        native_counts["anchored_phase"]["lane_calls"] == old_counts["anchored_phase"]["lane_calls"],
        paid_selected_short=selection["refinement_attempts"] < old_selection["refinement_attempts"] and
        selection["refinement_attempts"] == retained_short,
        named_finish=finish["status"] == old["solver"]["route_details"]["named_survivor_fit"]["status"] == "accepted",
        arms=verified["arms"] == old_verified["arms"], owners=verified["owners"] == old_verified["owners"] and
        roles == old["owners"], grid_path=verified["scientific_digests"] == old_verified["scientific_digests"],
        figures=all(all(checks.values()) for checks in plots.values()))
    write(root / "sealed.json", dict(binding_sha256=sha256((root / "binding.json").read_bytes()).hexdigest(),
          candidate=candidate, packet=str(packet), clock=clock, cache=cache, guarded_pins=GUARDED_PINS,
          factors=factors, comparisons=parity, plots=plots, roles=roles, raw=bootstrap, solver=dict(
              route=research["route"], solve=research["solve"], route_details=research["route_details"]),
          controls=dict(guarded_clock=old["clock"], named_clock=stock["clock"], guarded_phases=old["raw"]["phases"],
                        guarded_native=old_counts, guarded_selection=old_selection)))

def score(root):
    from north_interlaced_raw import NORTH, TRUTH_SHA
    from tools.pipeline_eval.qualification.score_paired_holdout import face_clearance_km
    from tools.pipeline_eval.scoring import distance_km

    sealed = root / "sealed.json"
    result = read(sealed)
    _, old = control()
    _, controls = references()
    key = json.loads(checked(HERE.parent / "regional-release/scoring-key.json", TRUTH_SHA))
    original_scores = json.loads(checked(GUARDED / "score.json", GUARDED_PINS["score"]))
    if original_scores["sealed_sha256"] != GUARDED_PINS["sealed"]:
        raise ValueError("Historical errors must bind the original guarded terminal")
    (truth,) = {tuple(row["truth"]) for row in key["answers"].values() if row["recording"] == NORTH}
    offer = result["candidate"]["verified"]["receipt"]["region"]
    clearance = face_clearance_km(offer, truth)
    if abs(clearance - 0.1) > 0.001:
        raise ValueError("The signed simulation must be in its original containing offer")
    outcomes = {}
    candidates = dict(continued=result["candidate"], guarded=old["candidate"], named=controls["stock"])
    for label, data in candidates.items():
        outcomes[label] = {arm: dict(position=values["latlon"], error_m=1000*distance_km(truth, values["latlon"]),
                                   rf_rms_hz=values["rf_rms_hz"], face_km=face_clearance_km(offer, values["latlon"]))
                           for arm, values in data["verified"]["arms"].items()}
    write(root / "score.json", dict(sealed_sha256=sha256(sealed.read_bytes()).hexdigest(), outcomes=outcomes,
                                   truth_face_km=clearance, scoring_key_sha256=TRUTH_SHA))


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("mode", choices=("launch", "seal", "score"))
    cli.add_argument("root", type=Path)
    args = cli.parse_args()
    if args.mode == "launch":
        control()
        launch(args.root, continued=True)
    elif args.mode == "seal":
        seal(args.root)
    else:
        score(args.root)
