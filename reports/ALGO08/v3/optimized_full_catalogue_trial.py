"""Publish one authenticated saved DS30-0374 run and compare its evidence."""

import argparse
from hashlib import sha256
import json
import os
from pathlib import Path
import subprocess
from time import perf_counter

from aperture_trial import ARMS, PAYLOAD, RELEASE, archive_identity, machine, read, write
from joint_publication import artifacts
from signed_0374_transfer import bind, owner_changes, verify_stock
from tools.pipeline_eval.qualification import paired_publication as pairs


HERE = Path(__file__).resolve().parent
FULL_SCORE = "2593328f9a58745bc4acbb9412acab2aa9a0477dd941bddffb1e0bf7b744e24d"
STOCK_SCORE = "6283dfb1e942af01e046d7723c6f8cd3366c8e5e00c2fcd8a6655a91a072afa1"
TOLERANCE = 1e-5


def published(output):
    from leo.storage.fast_standard_analysis import FastStandardAnalysisStore

    path = output / "joint-research-receipt.json"
    result = read(path)
    receipt = result["receipt"]
    rendered = artifacts(output, receipt)
    if json.loads(json.dumps(rendered)) != result["evidence"]:
        raise ValueError("Publication figure or evidence hashes changed")
    evidence = pairs.evidence(output, receipt, started_ns=0, read_only=True)
    store = FastStandardAnalysisStore(output)
    grid = store.position_grid(receipt["run_id"]) if receipt["decision"] == "complete" else None
    return result, evidence, grid, sha256(path.read_bytes()).hexdigest()


def run(output):
    host = machine()
    if (host["cpu"] != [2] or host["nice"] < 15 or "prio 7" not in host["ionice"]
            or any(n != "1" for n in host["threads"].values())):
        raise ValueError("Single low-priority core required")
    pair, expected, saved, region, archive, _ = bind()
    output.mkdir(exist_ok=False)
    environment = dict(os.environ, PYTHONPATH=os.pathsep.join(map(str, (HERE, PAYLOAD, RELEASE / "src", RELEASE))),
                       MPLCONFIGDIR=str(output / "fonts"))
    for key in ("ALGO08_EVALUATION_LATITUDE", "ALGO08_EVALUATION_LONGITUDE",
                "ALGO08_REGION_FILE", "ALGO08_EXPERIMENT_CONFIG"):
        environment.pop(key, None)
    python = str(RELEASE / "venv/bin/python")
    subprocess.run([python, "-Bc", "from matplotlib import font_manager; font_manager.findfont('DejaVu Sans')"],
                   env=environment, check=True, timeout=20)
    started, before = perf_counter(), pairs.child_usage()
    child = subprocess.run([python, "-BPs", str(HERE / "joint_publication.py"),
                    "--recording", pair["recording"], "--archive", str(archive), "--region", str(region),
                    "--saved", str(saved), "--saved-digest", expected["witnesses"]["detection_sha256"],
                    "--optimized-full-catalogue", "--verify-images", "--output", str(output / "publication")],
                    env=environment, text=True, capture_output=True, timeout=90)
    clocks = dict(elapsed_s=perf_counter()-started,
                  **{key: value-before[key] for key, value in pairs.child_usage().items()})
    write(output / "process.json", dict(clocks=clocks, machine=host, exit_code=child.returncode))
    if child.returncode:
        raise RuntimeError(child.stderr[-4000:])


def verified_report(filename, expected):
    raw = (HERE / "measurements" / filename).read_bytes()
    if sha256(raw).hexdigest() != expected:
        raise ValueError(f"Archived comparison changed: {filename}")
    return json.loads(raw)


def figures(before, after):
    from leo.contracts.fast_standard_analysis import PLOTS

    return {key: dict(bytes=before[key]["sha256"] == after[key]["sha256"],
                      pixels=before[key]["rgba_sha256"] == after[key]["rgba_sha256"],
                      size=tuple(before[key]["size"]) == tuple(after[key]["size"]))
            for key in PLOTS if key in before and key in after}


def grid_errors(full, candidate):
    import numpy as np

    maxima = dict.fromkeys(ARMS)
    minima = dict.fromkeys(ARMS)
    if full is None or candidate is None:
        return dict(complete=False, equal_metadata=False, equal_coordinates=False, max_abs_error=maxima, minima=minima)
    omit = {"binding", "elapsed_seconds", "points"}
    metadata = [{key: value for key, value in grid.items() if key not in omit} for grid in (full, candidate)]
    coordinates = [[{key: value for key, value in point.items() if key != "scores"}
                    for point in grid["points"]] for grid in (full, candidate)]
    if coordinates[0] == coordinates[1] and coordinates[0]:
        for arm in ARMS:
            values = np.array([[p["scores"][arm] for p in grid["points"]] for grid in (full, candidate)], float)
            if np.isfinite(values).all():
                maxima[arm] = float(np.max(np.abs(values[0]-values[1])))
                minima[arm] = [int(np.argmin(row)) for row in values]
    return dict(complete=bool(full["complete"] and candidate["complete"]), equal_metadata=metadata[0] == metadata[1],
                equal_coordinates=coordinates[0] == coordinates[1], max_abs_error=maxima, minima=minima)


def score(output, full_control, stock_control, destination):
    from aperture_score import PHYSICAL, distance_km
    from leo.contracts.digests import canonical_digest

    pair, stock, _, _, archive, stock_plots = bind()
    old = verified_report("full-family-web-DS30-0374.json", FULL_SCORE)
    official = verified_report("signed-DS30-0374-publication.json", STOCK_SCORE)
    full, full_evidence, full_grid, full_sha = published(full_control)
    incumbent, stock_evidence, stock_grid, stock_sha = published(stock_control)
    candidate, evidence, grid, candidate_sha = published(output / "publication")
    verify_stock(stock_evidence, stock, incumbent["evidence"], json.loads(json.dumps(stock_plots)))
    if (full_sha != old["sealed_receipt_sha256"] or full.get("optimized_full_catalogue", False)
            or not full["full_catalogue"] or full["evidence"] != old["rendered"]
            or stock_sha != official["runs"]["stock"]["runner_receipt_sha256"] or not incumbent["stock_control"]
            or not candidate["optimized_full_catalogue"] or not candidate["full_catalogue"]
            or archive_identity(archive) != pair["archive"]):
        raise ValueError("Expected the sealed original publication and the new optimized route")

    witness = stock["witnesses"]
    for result, observed, root in ((full, full_evidence, full_control), (incumbent, stock_evidence, stock_control),
                                  (candidate, evidence, output / "publication")):
        native, = (root / "fast-scan-automatic-work").glob("*/detections.json")
        if (result["input"] != "saved detector" or result["saved_digest"] != witness["detection_sha256"]
                or result["saved_handoff_manifest"] != witness["input_manifest_sha256"]
                or canonical_digest(read(native)) != witness["detection_sha256"]
                or observed["raw_authority"] != stock["raw_authority"]
                or result["receipt"]["region"] != stock["receipt"]["region"]):
            raise ValueError("Authority, exact saved detections or original region changed")

    if sha256(PHYSICAL.read_bytes()).hexdigest() != official["reference_sha256"]:
        raise ValueError("Survey reference changed")
    survey, = [row["reference"] for row in read(PHYSICAL)["cases"]
               if row["dataset_label"] == official["case"] and row["authority_eligible"]]
    truth = [survey[k] for k in ("latitude_deg", "longitude_deg")]
    errors = {arm: None if evidence["arms"][arm]["latlon"] is None else distance_km(evidence["arms"][arm]["latlon"], truth)
              for arm in ARMS}
    deltas = {arm: None if errors[arm] is None else errors[arm]-official["horizontal_error_km"]["stock"][arm]
              for arm in ARMS}
    match = {key: evidence[key] == full_evidence[key] for key in ("arms", "owners", "reason")}
    match.update(decision=candidate["receipt"]["decision"] == full["receipt"]["decision"] == "complete",
                 exact_rows=candidate["selected_rows"] == full["selected_rows"],
                 path=candidate["evidence"].get("path") == full["evidence"].get("path"),
                 replay=candidate["solve"].get("objective_replay") == full["solve"].get("objective_replay"))
    observed_route, full_route = candidate["route_details"], full["route_details"]
    for key in ("exterior", "support", "signed"):
        match[key] = observed_route.get(key) == full_route.get(key)
    tested_cold, reference_cold = observed_route.get("cold", {}), full_route["cold"]
    match["cold_winner"] = all(tested_cold.get(k) == reference_cold[k]
                               for k in ("branch", "east_north_km", "latlon", "catalogue"))
    tested_scores, full_scores = tested_cold.get("scores", []), reference_cold["scores"]
    match["cold_completed_scores"] = len(tested_scores) == len(full_scores) and all(
        new is None or new == old for new, old in zip(tested_scores, full_scores, strict=True))
    grid_match = grid_errors(full_grid, grid)
    images = figures(full["evidence"]["images"], candidate["evidence"]["images"])
    grid_pass = (all(grid_match[k] for k in ("complete", "equal_metadata", "equal_coordinates"))
                 and all(v is not None and v <= TOLERANCE for v in grid_match["max_abs_error"].values())
                 and all(v is not None and v[0] == v[1] for v in grid_match["minima"].values()))
    grid_calls = candidate["solve"].get("reduced_grid", {})
    kernel_bound = grid_calls.get("reduced_calls", 0) > 0 and not grid_calls.get("unsupported_binding", 0)
    names = ("publication_cpu_s", "publication_elapsed_s")
    clocks = {mode: dict(solve=result["solve"], posterior_grid_handoff=result["receipt"]["posterior_grid_handoff"],
                         **{name: result[name] for name in names})
              for mode, result in (("stock", incumbent), ("full", full))}
    write(destination, dict(case=official["case"], archive=pair["archive"], raw_authority=stock["raw_authority"],
          saved_digest=witness["detection_sha256"], candidate_receipt_sha256=candidate_sha,
          full_receipt_sha256=full_sha, stock_receipt_sha256=stock_sha,
          full_score_sha256=FULL_SCORE, stock_score_sha256=STOCK_SCORE, historical_clocks=clocks,
          candidate=candidate, process=read(output / "process.json"), match_full=match, grid_match=grid_match,
          grid_vs_stock=grid_errors(stock_grid, grid), grid_tolerance=TOLERANCE, reduced_grid_bound=kernel_bound,
          candidate_error_km=errors, stock_error_km=official["horizontal_error_km"]["stock"],
          full_error_km=old["error_km"], delta_error_km=deltas, full_owners=owner_changes(full, candidate),
          stock_owners=owner_changes(incumbent, candidate),
          stock_owner_digests=stock["owners"], full_owner_digests=full_evidence["owners"],
          candidate_owner_digests=evidence["owners"], figures_vs_full=images,
          figures_vs_stock=figures(stock_plots["images"], candidate["evidence"]["images"]),
          pass_quality=(all(match.values()) and grid_pass and len(images) == 8
                        and all(v["size"] and v["pixels"] for v in images.values())
                        and all(v is not None and v <= .25 for v in deltas.values()))))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    subs = parser.add_subparsers(dest="action", required=True)
    subs.add_parser("run").add_argument("output", type=Path)
    scorer = subs.add_parser("score")
    for name in ("output", "full_control", "stock_control", "destination"):
        scorer.add_argument(name, type=Path)
    args = vars(parser.parse_args())
    (run if args.pop("action") == "run" else score)(**args)
