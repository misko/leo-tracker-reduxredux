"""Score the four authenticated dense detector and graph combinations."""

import argparse
import gzip
from hashlib import sha256
import json
from pathlib import Path

from aperture_trial import ARMS, inputs, read, write
from dense_full_short_crossover import CASE, HERE, file_sha
from dense_quadratic_proxy_score import owner_deltas
from full_short_crossover import compare_owners, normalized_owners


REFERENCE = HERE.parents[1] / "2026_11_21_ds30_full/reference-audit.json"
REFERENCE_PIN = "c055e43a03d22379c0bde7e136cb786efae1fe6a31919cc1e3ecea32637840b5"
INSTALLED = ("dense-geographic-kernel.json.gz", "60c7942280d425ab2e808b7913da460283a821a26046dcb6befd1d3816dbabbf")
QUADRATIC = ("dense-quadratic-fused.json.gz", "f9e61aa3c37a1a62bd708185feb39e6a7c9706326f3819aba2e892cb57061f06")
EDGES = {"detector_on_installed_graph": ("installed_installed", "short_installed"),
         "detector_on_quadratic_graph": ("installed_quadratic", "short_quadratic"),
         "graph_on_installed_detector": ("installed_installed", "installed_quadratic"),
         "graph_on_short_detector": ("short_installed", "short_quadratic"),
         "combined": ("installed_installed", "short_quadratic")}


def pinned_receipt(receipt):
    name, pin = receipt
    body = (HERE / "measurements" / name).read_bytes()
    if sha256(body).hexdigest() != pin:
        raise ValueError(f"A fused saved comparator changed at {name}")
    return json.loads(gzip.decompress(body))


def locate_candidate(root, expected):
    from leo.contracts.digests import canonical_digest

    research_path = root / "joint-research-receipt.json"
    research = read(research_path)
    run = research["receipt"]["run_id"]
    detected, = (root / "fast-scan-automatic-work").glob("*/detections.json")
    terminal = root / "fast-scan-automatic-work" / run / "terminal.json"
    paths = (research_path, detected, terminal, root / "full-short-recipe.json", root.parent / "binding.json",
             root.parent / "process.json")
    if {path.name: file_sha(path) for path in paths} != expected["files_sha256"]:
        raise ValueError("The original raw seals changed across the saved solve")
    native = read(detected)
    if canonical_digest(native) != expected["raw_native_sha256"]:
        raise ValueError("Expected the original signed native document")
    return native


def validate_controls(stock, quadratic, saved):
    original, short = saved["holder"], saved["raw_result"]
    binary = saved["fused_geography_sha256"]
    if (stock["identity"] != original or quadratic["identity"] != original
            or stock["build"]["binary_sha256"] != binary or quadratic["fused_geography"]["binary_sha256"] != binary
            or any(row["regional"][0]["result"]["snapshots"] != saved["archive_snapshots"]
                   for row in (stock, quadratic, short))):
        raise ValueError("All four cells require the same frozen archive, offer and fused geographic release")


def describe(row, truth, scope):
    from tools.pipeline_eval.scoring import distance_km

    points = (row.get("grid") or {}).get("points", [])
    region, = row["regional"]
    attempts = row["attempts"]
    attempt = attempts[0] if attempts else {}
    signed = attempt.get("warm_signed_fit", {})
    cold = attempt.get("cold", {})
    arms = {}
    for arm in ARMS:
        values = row["arms"].get(arm, {})
        position = values.get("latlon")
        residual = values.get("rf_rms_hz")
        arms[arm] = dict(latlon=position, rf_rms_hz=residual,
                         horizontal_error_km=None if position is None else distance_km(position, truth),
                         owners=row.get("associated", {}).get(arm),
                         grid_minimum=min(range(len(points)), key=lambda i: points[i]["scores"][arm]) if points else None)
    return dict(arms=arms, status=row["status"], reason=row.get("reason"),
                solve={k: row["solve"][k] for k in ("cpu_s", "elapsed_s")}, solve_scope=scope,
                graph=dict(observations=region["result"]["original_points"], tracks=region["result"]["track_count"],
                           points=region["result"]["graph_points"], active_curvature=row.get("graph", {}).get("active_curvature")),
                geography=region, projection=row.get("native_projection") or row.get("native") or
                row.get("fused_geography", {}).get("counts") or row["solve"].get("geographic_projector"),
                route=row.get("route", attempt.get("decision", row["status"])), cold_route=cold.get("routing"),
                finalist_fits=len(cold.get("completed", ())), warm_fit={k: v for k, v in signed.items() if k != "finished_arms"},
                fallback=attempt.get("fallback_clocks"), late_exterior=attempt.get("exterior"),
                stage_clocks={k: v for k, v in attempt.items() if k.endswith("_clocks")},
                grid_points=row.get("grid_points"), objective_replay=row.get("objective_replay"))


def deltas(baseline, candidate, delta_owners=None, common_grid=None):
    from tools.pipeline_eval.scoring import distance_km

    changes = {}
    for arm in ARMS:
        before, after = (row["arms"][arm] for row in (baseline, candidate))
        change = {name: None if (before[name] is None or after[name] is None) else after[name] - before[name]
                  for name in ("horizontal_error_km", "rf_rms_hz")}
        points = [row["latlon"] for row in (before, after)]
        changes[arm] = dict(change, endpoint_shift_km=distance_km(*points) if all(points) else None)
    screen = all(row["horizontal_error_km"] is not None and row["horizontal_error_km"] <= .25 for row in changes.values())
    return dict(arms=changes, no_arm_worse_than_250_m=screen, owners=delta_owners, common_grid_coordinates=common_grid,
                solve_cpu_delta_s=candidate["solve"]["cpu_s"]-baseline["solve"]["cpu_s"],
                solve_elapsed_delta_s=candidate["solve"]["elapsed_s"]-baseline["solve"]["elapsed_s"])


def score(raw, replay_path, destination):
    saved = read(replay_path)
    evidence = saved["raw"]
    original = evidence["raw_result"]
    native = locate_candidate(raw, evidence)
    incumbent_native, _, _, _, identity = inputs(CASE)
    if identity != evidence["holder"] or file_sha(REFERENCE) != REFERENCE_PIN:
        raise ValueError("The original installed input or post-solve survey reference changed")
    survey, = [row["reference"] for row in read(REFERENCE)["cases"] if row["dataset_label"] == CASE and row["authority_eligible"]]
    truth = [survey[k] for k in ("latitude_deg", "longitude_deg")]
    first = pinned_receipt(INSTALLED)["dense-full"]
    first["solve"] = first["measure"]
    second = pinned_receipt(QUADRATIC)
    validate_controls(first, second, evidence)
    runs = dict(installed_installed=first, installed_quadratic=second, short_installed=saved, short_quadratic=original)
    report = {key: describe(row, truth, "raw publication solve subclock" if key == "short_quadratic"
                            else "saved numerical solve through the grid") for key, row in runs.items()}
    for key, row in report.items():
        row["native_sha256"] = evidence["raw_native_sha256"] if key.startswith("short") else identity["native_sha256"]
    edges = {}
    for key, (a, b) in EDGES.items():
        delta_owners = None
        if runs[a]["status"] == runs[b]["status"] == "ok":
            rows = [runs[k]["selected_rows"] for k in (a, b)]
            if report[a]["native_sha256"] == report[b]["native_sha256"]:
                delta_owners = {arm: owner_deltas(rows[0][arm], rows[1][arm]) for arm in ARMS}
            else:
                physical = [normalized_owners(native if k.startswith("short") else incumbent_native, owned)
                            for k, owned in zip((a, b), rows, strict=True)]
                delta_owners = compare_owners(*physical)
        coords = [{tuple(p["latlon"]) for p in (runs[k].get("grid") or {}).get("points", [])} for k in (a, b)]
        edges[key] = deltas(report[a], report[b], delta_owners, len(coords[0] & coords[1]))

    effects = {}
    for arm in ARMS:
        graph_changes = [edges[k]["arms"][arm]["horizontal_error_km"]
                         for k in ("graph_on_short_detector", "graph_on_installed_detector")]
        effects[arm] = None if None in graph_changes else graph_changes[0] - graph_changes[1]
    summary = dict(case=CASE, identity=identity, fused_projection_sha256=evidence["fused_geography_sha256"],
                   runs=report, deltas=edges, graph_detector_interaction_km=effects,
                   raw_process=evidence["process"], raw_publication=original["publication"],
                   raw_acquisition=read(raw / "full-short-recipe.json")["receiver_audit"]["acquire"],
                   raw_artifacts=original["science"], raw_binding_pins=evidence["files_sha256"],
                   owner_comparison="native observation identity, with cross-detector counts matched by receiver, RF, edge and counter",
                   receipt_sha256=file_sha(replay_path), comparator_sha256=dict([INSTALLED, QUADRATIC]),
                   reference_sha256=REFERENCE_PIN)
    write(destination / "summary.json", summary)
    with (destination / "full.json.gz").open("xb") as stream:
        stream.write(gzip.compress(json.dumps(dict(summary=summary, saved_replay=saved), separators=(",", ":"),
                                             allow_nan=False).encode(), mtime=0))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("raw", "replay_path", "destination"):
        parser.add_argument(name, type=Path)
    score(**vars(parser.parse_args()))
