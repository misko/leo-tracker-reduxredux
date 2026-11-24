"""Read back the paired DS30-0359 publication from its prediction seal."""

import argparse
import json
from pathlib import Path

from reports.ALGO08.v3.ds30_0359_predictive_grid import BASE, JOB_PIN, PRIOR_PIN, READY, digest, read


def image_identity(original, candidate):
    return {name: (item["sha256"] == candidate[name]["sha256"]
                   and item["rgba_sha256"] == candidate[name]["rgba_sha256"]
                   and tuple(item["size"]) == tuple(candidate[name]["size"]))
            for name, item in original.items()}


def scaled_clocks(trace):
    result = {}
    for key in ("cpu", "wall"):
        stock = trace[f"stock_predictive_{key}_ns"] / 1e9
        candidate = trace[f"candidate_predictive_{key}_ns"] / 1e9
        both = trace[f"paired_grid_{key}_ns"] / 1e9
        result[key] = dict(stock_predictor_s=stock, reduced_predictor_s=candidate, measured_saving=stock-candidate,
                           paired_grid_s=both, common_grid_and_observer_s=both-stock-candidate,
                           estimated_stock_grid_s=both-candidate, estimated_reduced_grid_s=both-stock)
    return result


def score(root):
    from aperture_trial import write
    from clean_saved_0169_trial import output_seal
    from clean_saved_publication import load_job
    from empty_bootstrap import checked
    from history_risk_cairo_physical import clean
    from leo.contracts.digests import canonical_digest
    from leo.storage.fast_standard_analysis import FastStandardAnalysisStore
    from prospective_0316_solver import inspect

    seal = root / "prediction-seal.json"
    if read(seal) != output_seal(root):
        raise ValueError("The two-kernel worker or its output changed after the prediction seal")
    prior = json.loads(checked(BASE / "result.json", PRIOR_PIN))
    old = prior["jobs"]["routed"]["publication"]
    clock, admission = read(root / "routed/clock.json"), read(root / "admission.json")
    result = dict(case="DS30-0359", prediction_sha256=digest(seal), measured_children=1, waveform_reads=0,
                  clock=clock, admission=admission, qualified=False, reference_geographic=prior["geographic"])
    if clock["exit_code"]:
        write(root / "result.json", result | {"status": "paired_worker_failed"})
        return
    directory = root / "routed/candidate"
    bound, req = load_job(READY / "job.json", JOB_PIN)
    receipt = read(directory / "worker.json")["receipt"]
    current = inspect(directory, "0359-paired-predictive", receipt, clock, req, native_sha=req["native_sha256"],
                      windows=bound["issued"], admitted=bound["admitted"], audit_name="worker.json")
    live = read(root / "paired-grid.json")
    grid = FastStandardAnalysisStore(directory).position_grid(receipt["run_id"])
    grid_body = {key: value for key, value in grid.items() if key not in ("binding", "elapsed_seconds")}
    paired_body = {key: value for key, value in live["candidate"].items() if key not in ("binding", "elapsed_seconds")}
    ports = read(directory / "ports.json")
    images = image_identity(old["figures"], current["figures"])
    checks = dict(
        exact_terminal=old["terminal"] == current["terminal"],
        exact_calibration=old["science"]["arms"] == current["science"]["arms"],
        exact_owners=old["selected_rows"] == current["selected_rows"] and all(len(rows) == 3640 for rows in current["selected_rows"].values()),
        exact_path=old["sidecars"]["path"] == current["sidecars"]["path"],
        exact_graph=clean(ports["graph"]) == clean(prior["candidate_traces"]["ports"]["graph"])
        and old["worker"]["graph_proof"] == current["worker"]["graph_proof"],
        exact_reconstructed_grid=old["sidecars"]["grid"]["scientific_sha256"] == live["checks"]["stock_grid_sha256"],
        actual_reduced_grid=grid_body == paired_body and canonical_digest(grid_body) == live["checks"]["candidate_grid_sha256"],
        exact_endpoint_replay=grid["endpoint_objective_replay"] == old["worker"]["solve"]["objective_replay"],
        complete_pair=len(live["calls"]) == 356 and grid["complete"] and grid["evaluated_points"] == 179,
        eight_exact_pngs=len(images) == 8 and all(images.values()),
    )
    original_kernel = old["worker"]["receipt"]["posterior_grid_handoff"]
    write(root / "result.json", result | dict(qualified=all(checks.values()), checks=checks, images=images,
          candidate=current, pairing=live, cost=scaled_clocks(live["clocks"]), archived_kernel=original_kernel,
          published_grid=read(root / "routed/combined-grid.json"), phases=receipt["posterior_grid_handoff"]))


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("root", type=Path)
    score(cli.parse_args().root)
