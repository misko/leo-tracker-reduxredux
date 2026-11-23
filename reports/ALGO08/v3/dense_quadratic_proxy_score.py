"""Compare the sealed original-graph and full-short quadratic numerical proofs."""

import argparse
import gzip
from hashlib import sha256
import json
from pathlib import Path

from aperture_trial import ARMS, read, write
from dense_quadratic_proxy import CONTROL_PIN, HERE, LIVE_ROUTE_PIN
from live_inference_profile_score import REFERENCE


ARCHIVED = HERE / "measurements/live-inference-profile.json.gz"
TRACK_ASSET_PIN = "a7a252b2fd9a9fe7c617f4565b171c159846705803f4fb80ab755ba9ea94710a"
ROUTE_MODULES = ("cold_finalist_race.py", "optimized_grid.py", "prepared_exterior.py", "early_region.py")
GRAPH_MODES = ("original", "endpoint", "endpoint", "original")


def owner_deltas(first, second):
    a, b = ({row[0]: tuple(row[1:]) for row in rows} for rows in (first, second))
    if len(a) != len(first) or len(b) != len(second):
        raise ValueError("Duplicate observation owner")
    shared = a.keys() & b.keys()
    return dict(common=len(shared), lost=len(a.keys() - b.keys()), new=len(b.keys() - a.keys()),
                same_satellite_and_role=sum(a[key] == b[key] for key in shared),
                changed_satellite=sum(a[key][0] != b[key][0] for key in shared),
                changed_role=sum(a[key][1] != b[key][1] for key in shared),
                family_counts=[len({row[0] for row in owners.values()}) for owners in (a, b)])


def verify_pair(control, quadratic):
    from full_short_raw import GRAPH

    graph = quadratic["graph"]
    installed, candidate = graph["control"], graph["quadratic"]
    actual_changes = {k: v for k, v in candidate.items() if installed.get(k) != v}
    if (set(installed) != set(candidate) or actual_changes != GRAPH
            or graph["track_asset_sha256"] != TRACK_ASSET_PIN or graph["live_route_sha256"] != LIVE_ROUTE_PIN
            or quadratic["identity"] != control["identity"] or quadratic["orbit_policy"] != control["orbit_policy"]
            or quadratic["grid_kernel"]["grid_calls"] != control["grid_kernel"]["grid_calls"]
            or any(quadratic["source_sha256"][name] != control["source_sha256"][name] for name in ROUTE_MODULES)):
        raise ValueError("Expected just the full-short quadratic graph change on the exact saved packet and route")
    for run in (control, quadratic):
        proof, = run["regional"]
        attempts, = run["attempts"]
        if (not run["grid"]["complete"] or len(run["grid"]["points"]) != run["grid_points"]
                or run["status"] != "ok" or attempts["decision"] != "complete"
                or proof["result"]["probes_evaluated"] != len(run["visited_probes"])
                or run["catalogue"].get("catalogue_handoff") != 1):
            raise ValueError("Expected both solver arms and original complete numerical evidence")


def graph_gate(directory, graph_digest):
    paths = [directory / f"graph-{i}-{mode}.json" for i, mode in enumerate(GRAPH_MODES, 1)]
    rows = [read(path) for path in paths]
    for mode, row in zip(GRAPH_MODES, rows, strict=True):
        if (row["graph_trial_mode"] != mode or row["graph"]["graph_sha256"] != graph_digest
                or (mode == "endpoint" and not row["kernel"].get("endpoint_checks"))
                or row["kernel"].get("original_checks") or row["kernel"].get("unsupported_module")):
            raise ValueError("The prepared Graph or endpoint routing changed")
    clocks = [row["graph"]["clocks"]["prepare_tracks"][0] for row in rows]
    cpu = [clk["cpu_s"] for clk in clocks]
    saved = [cpu[0] - cpu[1], cpu[3] - cpu[2]]
    mean = sum(saved) / 2
    return dict(graph_sha256=graph_digest, clocks=clocks, saved_by_pair_cpu_s=saved, mean_saved_cpu_s=mean,
                full_replay_allowed=min(saved) > 0 and mean >= .15,
                inputs_sha256={path.name: sha256(path.read_bytes()).hexdigest() for path in paths}), rows


def compare(directory):
    from tools.pipeline_eval.scoring import distance_km

    source = ARCHIVED.read_bytes()
    if sha256(source).hexdigest() != CONTROL_PIN:
        raise ValueError("The sealed original live comparison changed")
    prior = json.loads(gzip.decompress(source))
    control = prior["runs"]["control"]
    path = directory / "quadratic.json"
    graph_profile_path = directory / "graph-profile.json"
    quadratic, profile = read(path), read(graph_profile_path)
    verify_pair(control, quadratic)
    graph_sha256 = quadratic["graph"]["graph_sha256"]
    if profile["graph"]["graph_sha256"] != graph_sha256:
        raise ValueError("Graph-only attribution disagrees with the measured full solve")
    if sha256(REFERENCE.read_bytes()).hexdigest() != prior["summary"]["reference_sha256"]:
        raise ValueError("The original survey reference changed")
    physical, = [row for row in read(REFERENCE)["cases"] if row["dataset_label"] == "DS30-0008"]
    if not physical["authority_eligible"]:
        raise ValueError("Expected the authenticated roof reference")
    truth = [physical["reference"][key] for key in ("latitude_deg", "longitude_deg")]

    def row(run):
        attempt, = run["attempts"]
        points = run["grid"]["points"]
        return dict(arms={arm: dict(run["arms"][arm], owners=run["associated"][arm],
                                    horizontal_error_km=distance_km(run["arms"][arm]["latlon"], truth),
                                    grid_minimum=min(range(len(points)), key=lambda i: points[i]["scores"][arm]))
                          for arm in ARMS}, solve=run["solve"], status=run["status"], reason=run["reason"],
                    grid_points=run["grid_points"], objective_replay=run["objective_replay"],
                    regional=run["regional"], grid_kernel=run["grid_kernel"],
                    clocks={k: v for k, v in attempt.items() if k.endswith("_clocks")},
                    fallback=attempt["decision"] == "fallback", cold=attempt["cold"]["routing"],
                    finished_finalists=len(attempt["cold"]["completed"]),
                    signed={k: v for k, v in attempt["warm_signed_fit"].items() if k != "finished_arms"})

    stock, candidate = row(control), row(quadratic)
    delta = {arm: dict(horizontal_error_km=candidate["arms"][arm]["horizontal_error_km"] - stock["arms"][arm]["horizontal_error_km"],
                       rf_rms_hz=candidate["arms"][arm]["rf_rms_hz"] - stock["arms"][arm]["rf_rms_hz"],
                       endpoint_shift_km=distance_km(candidate["arms"][arm]["latlon"], stock["arms"][arm]["latlon"]),
                       owners=owner_deltas(control["selected_rows"][arm], quadratic["selected_rows"][arm]))
             for arm in ARMS}
    old_nodes, new_nodes = ({tuple(p["latlon"]) for p in run["grid"]["points"]} for run in (control, quadratic))
    stages = ("prepare_tracks", "graph_tracks", "_best_piece", "_bounded_slope", "_path_models", "finish_lane",
              "lstsq", "legroots", "_piece", "_supported", "scoped_lane")
    graph, graph_rows = graph_gate(directory, graph_sha256)
    endpoint = None
    exact = None
    endpoint_path = directory / "endpoint-full.json"
    if graph["full_replay_allowed"]:
        from live_inference_profile_score import comparison

        endpoint = read(endpoint_path)
        verify_pair(control, endpoint)
        exact = comparison(quadratic, endpoint)
        exact["graph"] = endpoint["graph"]["graph_sha256"] == graph_sha256
        exact["endpoint_gate"] = endpoint["kernel"] == graph_rows[1]["kernel"] == graph_rows[2]["kernel"]
        if not all(exact.values()):
            raise ValueError(f"Endpoint specialization changed the complete result: {exact}")

    summary = dict(input=control["identity"], original_live=stock, quadratic_live=candidate, arm_deltas=delta,
                   c_arm_250_m_screen=all(x["horizontal_error_km"] <= .25 for x in delta.values()),
                   no_worse_both_arms=all(x["horizontal_error_km"] <= 0. for x in delta.values()),
                   original_profiled_graph_cpu_s=next(r["inclusive_s"] for r in prior["runs"]["profile"]["profile"]
                                                      if r["function"] == "prepare_tracks"),
                   quadratic_graph=quadratic["graph"], common_grid_coordinates=len(old_nodes & new_nodes),
                   reference_clearance_km=prior["summary"]["offer_clearance_km"],
                   quadratic_graph_profile=[r for r in profile["profile"] if r["function"] in stages],
                   graph_endpoint_gate=graph, endpoint_live=None if endpoint is None else row(endpoint),
                   endpoint_full_exact=exact,
                   files_sha256={p.name: sha256(p.read_bytes()).hexdigest() for p in (path, graph_profile_path, ARCHIVED, REFERENCE)})
    if endpoint is not None:
        summary["files_sha256"][endpoint_path.name] = sha256(endpoint_path.read_bytes()).hexdigest()
    # Older receipts attempted to read a lane-only counter from each final track.
    summary["quadratic_graph"] = {k: v for k, v in summary["quadratic_graph"].items() if k != "path_extracted"}
    write(directory / "scored-summary.json", summary)
    with (directory / "scored-full.json.gz").open("xb") as stream:
        stream.write(gzip.compress(json.dumps(dict(summary=summary, quadratic=quadratic, graph_profile=profile,
                                                    graph_repeats=graph_rows, endpoint=endpoint),
                                             separators=(",", ":"), allow_nan=False).encode(), mtime=0))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    compare(parser.parse_args().directory)
