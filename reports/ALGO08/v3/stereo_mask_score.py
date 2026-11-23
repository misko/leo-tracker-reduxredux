"""Join all sealed stereo-mask publications to independent evaluation positions."""

import argparse
from bisect import bisect_right
import gzip
from hashlib import sha256
import json
from pathlib import Path

from aperture_score import PHYSICAL, SIMULATED, distance_km, references
from aperture_trial import ARMS, read, write
from dense_full_short_raw import checked
from late_prefix_stop_score import compare, has_complete_evidence, passes
from signed_0374_transfer import owner_changes
from stereo_mask_trial import HERE, ORDER


PINS = {PHYSICAL: "c055e43a03d22379c0bde7e136cb786efae1fe6a31919cc1e3ecea32637840b5",
        SIMULATED: "0bda865a20e62852220a9ab8df63895a449bf203a2deb5370920dc3ce215d37d"}
PREFIX_MEMBERS_SHA = "4e3c020254a6b94f66f8e1bef39e4b475068d4c6658332cd22122d794cfc6dec"


def member_revisit(members, skipped):
    stops = tuple(row["stop"] for row in members)
    if not stops or len(set(stops)) != len(stops) or sorted(stops) != list(stops):
        raise ValueError("Expected ordered signed member boundaries")
    touched = {bisect_right(stops, visit) for visit, _ in skipped}
    if any(visit < 0 for visit, _ in skipped) or len(stops) in touched:
        raise ValueError("Unpaid slot outside the signed capture")
    return dict(revisit_members=len(touched), total_members=len(stops), member_ids=sorted(touched),
                **{key+"_bytes":sum(members[i][key] for i in touched) for key in ("compressed", "decoded", "index")})


def charge(original_solve_s, new_solve_s, budget, planner):
    reuse = budget["estimated_omitted_native_cpu_s"]
    direct = original_solve_s - new_solve_s + reuse - planner
    return dict(hypothetical_nonnative_fixed_cpu_s=budget["fixed_nonnative_acquisition_cpu_s"],
                saved_fit_delta_cpu_s=original_solve_s-new_solve_s, projected_direct_net_cpu_s=direct,
                projected_success_acquire_and_solve_cpu_s=budget["modeled_total_acquisition_cpu_s"]+new_solve_s+planner,
                gross_omitted_short_cpu_s=reuse, projected_minimum_retry_extra_cpu_s=reuse+original_solve_s,
                projected_retry_cost_over_original_cpu_s=new_solve_s+planner,
                optimistic_retry_rate_break_even=max(0, direct)/(reuse+original_solve_s))


def row(result, controls, binding, reference):
    observed, mask, budget = (result[name] for name in ("result", "mask", "budget"))
    terminal, solve, evidence = (observed[key] for key in ("terminal", "solve", "evidence"))
    full = controls["full"]
    peers = {kind: controls[kind]["arms"] for kind in ("full", "named")} if full["state"] == "complete" else {}
    arms = compare(terminal["arms"], peers, reference, binding["offer"])
    complete = has_complete_evidence(terminal, solve, evidence)
    separation = distance_km(*(terminal["arms"][arm]["latlon"] for arm in ARMS)) if complete else None
    any_proof = observed["early_regional"][-1]["result"]
    dropped = set(mask["lost_positive_ids"])
    owners = owner_changes(full, observed)
    for arm in ARMS:
        before = {r[0] for r in full["selected_rows"].get(arm, [])}
        owners[arm]["directly_omitted"] = len(before & dropped)
        owners[arm]["missing_although_sampled"] = owners[arm]["removed"] - owners[arm]["directly_omitted"]
        if complete and peers:
            arms[arm]["endpoint_shift_from_full_km"] = distance_km(terminal["arms"][arm]["latlon"], full["arms"][arm]["latlon"])
    measurements = charge(full["solve"]["cpu_s"], solve["cpu_s"], budget, mask["plan_and_history_audit_cpu_s"])
    return dict(arms=arms, owners=owners, complete=complete, passed=bool(peers) and passes(arms, complete), route=observed["route"],
                status=terminal["decision"], reason=terminal["reason"], separation_km=separation,
                mask={k:v for k,v in mask.items() if k not in {"skipped_slots", "lost_positive_ids"}},
                process=result["process"], budget=budget, measurements=measurements,
                solve_cpu_s=solve["cpu_s"], solve_elapsed_s=solve["elapsed_s"], grid_points=solve.get("grid_points", 0),
                image_count=len(evidence["images"]), path_sha256=evidence.get("path"), grid_sha256=evidence.get("grid"),
                graph_cpu_s=sum(values["cpu_s"] for values in observed["graph"]), tracks=any_proof.get("track_count"),
                early_regional=observed["early_regional"], fallback=(observed["route_details"] or {}).get("fallback_clocks"),
                terminal_sha256=observed["terminal_sha256"])


def score(root, far):
    # All complete saved artifacts seal before importing the reference data into the scoring step.
    sealed = {case: {mode: read(root / case / f"{mode}-sealed.json") for mode in modes} for case, modes in ORDER.items()}
    for source, pin in PINS.items():
        checked(source, pin)
    truth = references()
    physical, = [r for r in read(PHYSICAL)["cases"] if r["dataset_label"] == "DS30-0016"]
    if not physical["authority_eligible"]:
        raise ValueError("Weak physical reference not eligible")
    truth["DS30-0016"] = tuple(physical["reference"][k] for k in ("latitude_deg", "longitude_deg"))
    archive = checked(HERE / "measurements/late-prefix-stop.json.gz", PREFIX_MEMBERS_SHA)
    with gzip.open(archive, "rt") as stream:
        dense_prefix = json.load(stream)["DS30-0008"]["binding"]["record"]
    reports = {}
    for case, modes in ORDER.items():
        directory = root / case
        frozen = read(directory / "binding.json")
        controls, binding = frozen["controls"], frozen["binding"]
        point = truth["south-containing" if case == "south" else case]
        scores = {mode:row(sealed[case][mode], controls, binding, point) for mode in modes}
        if case == "DS30-0008":
            source = dense_prefix["binding"]
            if (source["raw_authority"] != binding["raw_authority"]
                    or source["native_sha256"] != binding["original_native_sha256"]):
                raise ValueError("Retried member inventory is from another recording or native packet")
            members = dense_prefix["controls"]["members"]
            for mode in modes:
                scores[mode]["dense_member_revisit"] = member_revisit(members, sealed[case][mode]["mask"]["skipped_slots"])
        reference = {kind: compare(controls[kind]["arms"], {}, point, binding["offer"]) for kind in ("full", "named")}
        full = controls["full"]
        endpoints = [sealed[case][mode]["result"]["terminal"]["arms"] for mode in modes]
        mask_separation = {arm: distance_km(*(r[arm]["latlon"] for r in endpoints))
                           for arm in ARMS} if all(r["complete"] for r in scores.values()) else None
        reports[case] = dict(scores=scores, reference=reference, binding=binding, full_solve_cpu_s=full["solve"]["cpu_s"],
                             full_grid_points=full["solve"]["grid_points"],
                             between_masks_separation_km=mask_separation,
                             frozen_sha256=sha256((directory / "binding.json").read_bytes()).hexdigest(),
                             receipt_sha256={m:sha256((directory / f"{m}-sealed.json").read_bytes()).hexdigest() for m in modes})
    qualified = next((m for m in ("target", "quarter") if all(r["scores"][m]["passed"] for r in reports.values())), None)
    omitted = None
    if far is not None:
        if qualified is None:
            raise ValueError("The containing panel did not qualify a far replay")
        frozen = read(far / "binding.json")
        replay = read(far / f"{qualified}-sealed.json")
        if replay["mask"]["native_sha256"] != reports["south"]["scores"][qualified]["mask"]["native_sha256"]:
            raise ValueError("South wave selection changed across regions")
        omitted = row(replay, frozen["controls"], frozen["binding"], truth["south-far"])
        omitted["passed"] = omitted["status"] == "withheld" and omitted["image_count"] == 0
    return dict(cases=reports, containing_qualified=qualified, far=omitted, member_source_sha256=PREFIX_MEMBERS_SHA,
                reference_pins={p.name:pin for p,pin in PINS.items()}, waveform_calls=0)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--far", type=Path)
    args = parser.parse_args()
    write(args.output, score(args.root, args.far))
