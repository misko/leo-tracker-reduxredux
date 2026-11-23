"""Check the sealed dense profile and paired saved geographic-proof replays."""

import argparse
import gzip
from hashlib import sha256
import json
from pathlib import Path

from aperture_trial import ARMS, read, write
from live_inference_profile import CASE


REFERENCE = Path(__file__).resolve().parents[2] / "2026_11_21_ds30_full/reference-audit.json"


def comparison(control, visible):
    fields = ("identity", "status", "reason", "orbit_policy", "arms", "owners", "selected_rows", "associated",
              "science", "grid", "grid_points", "objective_replay", "visited_probes")
    checks = {key: control[key] == visible[key] for key in fields}
    checks["visited_probes"] &= bool(control["visited_probes"])
    checks["region_proof"] = [{k: v for k, v in row.items() if k != "cpu_s"} for row in control["regional"]] == [
        {k: v for k, v in row.items() if k != "cpu_s"} for row in visible["regional"]]
    validation = ("support", "finish", "signed", "decision", "reason", "exterior")
    checks["solver_validation"] = all(control["attempts"][0].get(k) == visible["attempts"][0].get(k) for k in validation)
    checks["same_source"] = control["source_sha256"] == visible["source_sha256"]
    return checks


def compare(directory):
    from tools.pipeline_eval.qualification.score_paired_holdout import face_clearance_km
    from tools.pipeline_eval.scoring import distance_km
    from paid_certified_trial import sealed

    paths = {mode: directory / f"{mode}.json" for mode in ("profile", "control", "visible")}
    runs = {mode: read(path) for mode, path in paths.items()}
    control, visible = runs["control"], runs["visible"]
    installed = sealed("installed")[CASE]["stock"]
    original_fields = ("native_sha256", "offer", "archive", "detector_sha256", "raw_authority")
    if any(installed["identity"][k] != control["identity"][k] for k in original_fields):
        raise ValueError("Historical installed solve used a different saved input")

    reference, = [row for row in read(REFERENCE)["cases"] if row["dataset_label"] == CASE]
    if not reference["authority_eligible"]:
        raise ValueError("The physical survey reference is ineligible")
    truth = [reference["reference"][k] for k in ("latitude_deg", "longitude_deg")]
    probes = visible["proof_kernel"]
    optimized = bool(probes["sparse_probes"] and probes["sparse_probes"] == len(visible["visited_probes"])
                     and not probes.get("dense_fallback_probes") and not probes.get("unsupported_kernel"))
    checks = comparison(control, visible)
    stats = dict(cpu_saved_s=control["solve"]["cpu_s"] - visible["solve"]["cpu_s"],
                 elapsed_saved_s=control["solve"]["elapsed_s"] - visible["solve"]["elapsed_s"],
                 early_proof_cpu_saved_s=control["regional"][0]["cpu_s"] - visible["regional"][0]["cpu_s"])
    name = "regional_reassignment.py"
    cuts = ("prepare_native_scan", "causal_probes", "rank", "partial_fits", "complete_packet", "evaluate_veto",
            "orbit_geometry", "evaluate_terminal", "score", "score_track", "contrast_log_ratio", "graph_tracks")
    stats["profile_attribution"] = [row for row in runs["profile"]["profile"]
                                    if row["function"] in cuts and (row["function"] != "score" or row["file"].endswith(name))]

    def report(run):
        points = (run.get("grid") or {}).get("points", [])
        attempt = (run.get("attempts") or [{}])[0]
        proof = (run.get("regional") or [None])[0]
        return dict(solve=run.get("solve", {k: run[k] for k in ("cpu_s", "elapsed_s")}),
                    status=run["status"], reason=run["reason"], owner_digests=run["owners"],
                    arms={arm: dict(run["arms"][arm], error_km=distance_km(run["arms"][arm]["latlon"], truth),
                                    owners=run["associated"][arm],
                                    grid_minimum=min(range(len(points)), key=lambda i: points[i]["scores"][arm]) if points else None)
                          for arm in ARMS}, grid_points=run["grid_points"], replay=run["objective_replay"], early_regional=proof,
                    proof_kernel=run.get("proof_kernel"), grid_kernel=run.get("grid_kernel"),
                    fallback=attempt.get("decision") == "fallback", route_clocks={k: v for k, v in attempt.items() if k.endswith("_clocks")})

    results = dict(case=CASE, input=control["identity"], offer_clearance_km=face_clearance_km(control["identity"]["offer"], truth),
                   runs={mode: report(run) for mode, run in dict(runs, installed=installed).items()}, matches=checks,
                   valid=all(checks.values()) and optimized and control["status"] == "ok",
                   savings=stats, reference_sha256=sha256(REFERENCE.read_bytes()).hexdigest(),
                   source_sha256=control["source_sha256"], receipts_sha256={mode: sha256(path.read_bytes()).hexdigest()
                                                                           for mode, path in paths.items()})
    write(directory / "summary.json", results)
    with (directory / "full.json.gz").open("xb") as target:
        target.write(gzip.compress(json.dumps(dict(summary=results, runs=runs), separators=(",", ":"),
                                              allow_nan=False).encode(), mtime=0))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    compare(parser.parse_args().directory)
