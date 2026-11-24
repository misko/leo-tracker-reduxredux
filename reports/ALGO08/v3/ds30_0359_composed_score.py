"""Verify the one clean DS30-0359 composed saved exit and its media."""

import argparse
import json
import math
from pathlib import Path

from reports.ALGO08.v3.ds30_0359_composed_saved import qualification
from reports.ALGO08.v3.ds30_0359_predictive_grid import BASE, JOB_PIN, PRIOR_PIN, READY, digest, read
from reports.ALGO08.v3.ds30_0359_predictive_score import image_identity

ARMS = ("c0", "fitted_c")
TOLERANCE = 1e-5


def grid_evidence(original, candidate):
    def structure(grid):
        common = {k: v for k, v in grid.items() if k not in ("binding", "elapsed_seconds", "points")}
        return common | {"points": [{k: v for k, v in point.items() if k != "scores"} for point in grid["points"]]}

    if structure(original) != structure(candidate):
        raise ValueError("Grid coordinates, bounds or failure fields changed")
    comparison = {}
    for arm in ARMS:
        prior, new = ([point["scores"][arm] for point in grid["points"]] for grid in (original, candidate))
        if any(not math.isfinite(value) for value in (*prior, *new)):
            raise ValueError("Expected finite paired likelihoods at all grid points")
        minima = [min(range(len(values)), key=values.__getitem__) for values in (prior, new)]
        difference = max(abs(a-b) for a, b in zip(prior, new, strict=True))
        comparison[arm] = dict(maximum_abs_delta=difference, minimizing_indices=minima,
                               changes=sum(a != b for a, b in zip(prior, new, strict=True)),
                               qualified=difference <= TOLERANCE and minima[0] == minima[1])
    return comparison


def score(root):
    from aperture_trial import write
    from clean_saved_0169_trial import output_seal
    from clean_saved_publication import load_job
    from empty_bootstrap import checked
    from history_risk_cairo_physical import clean
    from leo.storage.fast_standard_analysis import FastStandardAnalysisStore
    from prospective_0316_solver import inspect

    seal = root / "prediction-seal.json"
    if read(seal) != output_seal(root):
        raise ValueError("The clean worker output changed after the prediction seal")
    before = json.loads(checked(BASE / "result.json", PRIOR_PIN))
    show = {mode: job["clock"] for mode, job in before["jobs"].items()}
    paired = qualification()
    clock, admission = read(root / "routed/clock.json"), read(root / "admission.json")
    result = dict(case="DS30-0359", prediction_sha256=digest(seal), measured_children=1, waveform_reads=0,
                  clock=clock, admission=admission, controls=show, qualified=False, reference_geographic=before["geographic"])
    if clock["exit_code"]:
        write(root / "result.json", result | {"status": "composed_worker_failed"})
        return

    directory = root / "routed/candidate"
    bound, req = load_job(READY / "job.json", JOB_PIN)
    receipt = read(directory / "worker.json")["receipt"]
    current = inspect(directory, "0359-composed", receipt, clock, req, native_sha=req["native_sha256"],
                      windows=bound["issued"], admitted=bound["admitted"], audit_name="worker.json")
    old = before["jobs"]["routed"]["publication"]
    grid = FastStandardAnalysisStore(directory).position_grid(receipt["run_id"])
    ordinary = FastStandardAnalysisStore(BASE / "routed/candidate").position_grid(old["science"]["receipt"]["run_id"])
    grid_check = grid_evidence(ordinary, grid)
    images = image_identity(old["figures"], current["figures"])
    telemetry = read(root / "composition.json")
    ports = read(directory / "ports.json")
    agg, png, predictive = (telemetry[key] for key in ("agg", "native_png", "predictive"))
    checks = dict(
        terminal=old["terminal"] == current["terminal"],
        calibration=old["science"]["arms"] == current["science"]["arms"],
        owners=old["selected_rows"] == current["selected_rows"] and all(len(rows) == 3640 for rows in current["selected_rows"].values()),
        graph=clean(ports["graph"]) == clean(before["candidate_traces"]["ports"]["graph"])
        and old["worker"]["graph_proof"] == current["worker"]["graph_proof"],
        path=old["sidecars"]["path"] == current["sidecars"]["path"],
        complete_grid=grid["complete"] and grid["evaluated_points"] == 179 and all(item["qualified"] for item in grid_check.values()),
        matches_paired_candidate=current["sidecars"]["grid"]["scientific_sha256"] == paired["pairing"]["checks"]["candidate_grid_sha256"],
        figures=len(images) == 8 and all(images.values()),
        agg=(agg.get("figures"), agg.get("axes"), agg.get("first_restores_elided")) == (2,16,2)
        and "ordinary_fallback" not in agg,
        native=(png["native"], png["fallback"], ports["png"]["verified"], ports["png"]["reused"]) == (8,0,8,8),
        reduced=(predictive.get("grid_calls"), predictive.get("reduced_calls")) == (1,356)
        and not predictive.get("original_fallback_calls") and not predictive.get("unsupported_binding"),
    )
    costs = {}
    for metric in ("elapsed_s", "cpu_s"):
        setup = admission["setup"][metric] + admission["smoke"]["clock"][metric]
        value, installed, routed = clock[metric], show["installed"][metric], show["routed"][metric]
        costs[metric] = dict(installed=installed, ordinary=routed, candidate=value, setup=setup,
                             candidate_charged=value+setup, savings_vs_ordinary=routed-value,
                             remaining_to_half=value-installed/2, speedup_vs_installed=installed/value)
    publication = read(directory / "joint-research-receipt.json")
    write(root / "result.json", result | dict(qualified=all(checks.values()), checks=checks, images=images,
          candidate=current, grid=grid_check, telemetry=telemetry, cost=costs, png_cache=ports["png"],
          renderer=read(root / "routed/render-usage.json"), measured_grid=read(root / "routed/combined-grid.json"),
          earlier_publication=before["publication_clocks"],
          publication={k: publication[k] for k in ("publication_cpu_s", "publication_elapsed_s", "solve")}))


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("root", type=Path)
    score(cli.parse_args().root)
