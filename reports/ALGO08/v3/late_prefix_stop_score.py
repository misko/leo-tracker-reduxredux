"""Join the sealed late-prefix results to the independent evaluation coordinates."""

import argparse
from pathlib import Path

from aperture_trial import ARMS, read
from dense_full_short_crossover import file_sha
from late_prefix_stop import HERE, ORDER


def compare(arms, reference, truth, offer):
    from aperture_score import distance_km, face_clearance_km

    result = {}
    for arm in ARMS:
        row = arms[arm]
        point, rms = row.get("latlon"), row.get("rf_rms_hz")
        if point is None:
            result[arm] = dict(error_km=None, rf_rms_hz=None, face_clearance_km=None, versus={})
            continue
        error = distance_km(point, truth)
        versus = {kind: dict(error_delta_km=error-distance_km(rows[arm]["latlon"], truth),
                             rf_delta_hz=rms-rows[arm]["rf_rms_hz"])
                  for kind, rows in reference.items()}
        result[arm] = dict(error_km=error, rf_rms_hz=rms, face_clearance_km=face_clearance_km(offer, point),
                           versus=versus)
    return result


def passes(arms, complete):
    return complete and all(rows["error_km"] is not None and all(
        rows["versus"][kind]["error_delta_km"] <= .25 for kind in ("full", "named")) for rows in arms.values())


def has_complete_evidence(terminal, solve, evidence):
    return (terminal["decision"] == "ok" and solve.get("grid_complete", False)
            and len(evidence["images"]) == 8)


def summary(root):
    from aperture_score import PHYSICAL, SIMULATED, distance_km, references
    from signed_0374_transfer import owner_changes

    truth = references()
    rows = {}
    for case, modes in ORDER.items():
        case_root = root / case
        sealed = read(case_root / "binding.json")
        controls, binding = sealed["controls"], sealed["binding"]
        references_matched = {kind: controls[kind]["arms"] for kind in ("full", "named")}
        point = truth["north-containing" if case == "north" else case]
        offer = binding["offer"]
        full, proof = controls["full"], controls["full"]["early_regional"][0]["result"]
        measured = {}
        endpoints = {}
        controls_score = {kind: compare(arms, references_matched, point, offer)
                          for kind, arms in references_matched.items()}
        for mode in modes:
            path = case_root / f"{mode}-sealed.json"
            run = read(path)
            entry = {k: run[k] for k in ("mask", "budget", "authentication", "failure", "process")}
            if run["failure"] is None:
                observed = run["result"]
                terminal, solve = observed["terminal"], observed["solve"]
                arms = compare(terminal["arms"], references_matched, point, offer)
                endpoints[mode] = terminal["arms"]
                details = observed["route_details"] or {}
                counts = observed["early_regional"][0]["result"]
                complete = has_complete_evidence(terminal, solve, observed["evidence"])
                entry.update(arms=arms, decision="complete" if complete else terminal["decision"],
                             terminal_status=terminal["decision"], reason=terminal["reason"], route=observed["route"],
                             passed=passes(arms, complete),
                             graph_cpu_s=sum(graph["cpu_s"] for graph in observed["graph"]),
                             narrow_graph=observed["graph_path"], preparation=solve["preparation"],
                             graph_points=counts.get("graph_points"), observations=counts.get("original_points"),
                             tracks=counts.get("track_count"), graph_ratio=counts.get("graph_points", 0)/proof["graph_points"],
                             solve_cpu_s=solve["cpu_s"], solve_elapsed_s=solve["elapsed_s"],
                             solve_ratio=solve["cpu_s"]/full["solve"]["cpu_s"],
                             projected_acquisition_plus_saved_solve_cpu_s=run["budget"]["modeled_total_acquisition_cpu_s"]+solve["cpu_s"],
                             ablation_endpoint_separation_km=distance_km(terminal["arms"]["c0"]["latlon"],
                                 terminal["arms"]["fitted_c"]["latlon"]) if complete else None,
                             fallback_clocks=details.get("fallback_clocks"), proof=observed["early_regional"],
                             grid_points=solve.get("grid_points", 0), image_count=len(observed["evidence"]["images"]),
                             selected={a: len(v) for a, v in observed["selected_rows"].items()},
                             owner_overlap=owner_changes(full, observed), terminal_sha256=observed["terminal_sha256"])
            else:
                entry["passed"] = False
            measured[mode] = dict(entry, sealed_sha256=file_sha(path))
        stability = {}
        if len(endpoints) == 2 and all(record[arm]["latlon"] is not None for record in endpoints.values() for arm in ARMS):
            stability = {a: distance_km(endpoints["half"][a]["latlon"], endpoints["three-quarters"][a]["latlon"])
                         for a in ARMS}
        rows[case] = dict(binding=binding, original_science=controls_score, original_graph_points=proof["graph_points"],
                          original_tracks=proof["track_count"], original_observations=proof["original_points"],
                          full_graph_path=full["graph_path"], full_solve_cpu_s=full["solve"]["cpu_s"],
                          named_process=controls["named"]["process"], prefixes=measured,
                          between_prefix_endpoints_km=stability)
    return dict(cases=rows, truth_sha256={path.name:file_sha(path) for path in (PHYSICAL, SIMULATED)},
                protocol_sha256=file_sha(HERE / "late-prefix-stop-protocol.md"))


if __name__ == "__main__":
    from json import dump

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    with args.output.open("x") as stream:
        dump(summary(args.root), stream, allow_nan=False, indent=2, sort_keys=True)
        stream.write("\n")
