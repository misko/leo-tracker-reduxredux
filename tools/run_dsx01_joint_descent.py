"""Stepwise position/identity descent over same-scan, radio-discovered hypotheses.

This finite lower-envelope search uses no fitted endpoints or evaluation site.
The 13 cold discovery receipts supply candidate label/alias combinations only;
all fitted nuisance state is discarded. Every hypothesis has a common zero
phase expansion, absolute priors, and the same original curved observations.
"""

import argparse
import hashlib
import json
import os
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import numpy as np
from associate_merged_track_catalogue import write
from compare_dsx01_frame_joint import actual_metrics
from dsx01_inference_audit import CENTER, InferenceReadGuard, disk_grid
from dsx01_radial_restarts import assignment_changes
from map_dsx01_clean_region import factory
from run_dsx01_clean_region import OUTPUT as CLEAN
from run_dsx01_clean_region import load_scan, zero_state

from leo.analysis.research.continuous_curve_fit import bounded_gauss_newton

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "reports/2026_10_18_dsx01_radial_restarts"
OUTPUT = ROOT / "reports/2026_10_18_dsx01_joint_descent"
CASES = tuple(f"DSX01-S0{k}" for k in range(1, 6))
ARMS = ("c0", "fitted_c")
STARTS = sorted(disk_grid(step_km=2)[1], key=lambda x: (float(np.linalg.norm(x)), *x))
MAX_STEPS = 64


def signature(node):
    rows = node["seed"]["rows"]
    values = [
        (r["component"], int(r["candidate_index"]), int(r["candidate_norad"]), int(a))
        for r, a in zip(rows, node["aliases"], strict=True)
    ]
    if len({r[0] for r in values}) != len(values):
        raise ValueError("duplicate fragment identity")
    return tuple(sorted(values))


def validate_discovery(record, case, audit):
    provenance = record["discovery_provenance"]
    if record.get("status") != "complete" or record.get("case") != case:
        raise ValueError("incomplete discovery or wrong scan")
    if (
        provenance.get("zero_initial_radio_phase_and_smooth") is not True
        or provenance.get("saved_atlas_labels_calibration_or_site_read") is not False
        or provenance.get("GPS_or_following_TLE_used") is not False
        or record.get("GPS_or_following_TLE_used") is not False
    ):
        raise ValueError("discovery must be cold, causal and independent of evaluation GPS")
    for key in ("bank_sha256", "cutoff_utc_ns", "origin_utc_ns", "candidate_count"):
        if record["input_audit"][key] != audit[key]:
            raise ValueError(f"discovery input mismatch: {key}")
    if provenance["candidate_count"] != audit["candidate_count"]:
        raise ValueError("candidate bank mismatch")


class JointReadGuard(InferenceReadGuard):
    def check_path(self, path):
        if isinstance(path, (str, bytes)):
            name = str(path)
            if name.startswith(str(SOURCE) + "/") and Path(name).name == "discovery.json":
                self.read_paths.add(name)
                return
        super().check_path(path)


def hypothesis_bank(scan, sigma):
    nodes, bindings, seen = [], {}, set()
    population = None
    for i in range(13):
        path = SOURCE / scan.case / "discovery" / f"start_{i:02d}" / "discovery.json"
        data = path.read_bytes()
        bindings[str(path.relative_to(ROOT))] = hashlib.sha256(data).hexdigest()
        record = json.loads(data)
        validate_discovery(record, scan.case, scan.inference_input_audit)
        node = dict(seed=dict(rows=record["seed"]["rows"], state=zero_state(scan)),
                    aliases=record["aliases"], source_start_id=i)
        key = signature(node)
        keys = {r[0] for r in key}
        if population is not None and keys != population:
            raise ValueError("all hypotheses must retain exactly the same fragment population")
        population = keys
        if key not in seen:
            seen.add(key)
            nodes.append(node)
    # No positional score, fitted phase, endpoint, GPS, or satellite whitelist
    # chooses which discovery survives: duplicate identities are identical here.
    return nodes, bindings


def score(problem, point):
    residual = problem.residual(np.asarray(point, float))
    return float(residual @ residual)


def descend(problems, start, *, max_steps=MAX_STEPS):
    """Minimize min_h J_h(x), checking every identity mode after every step.

    A damped step decreases its active branch. Rescoring every mode can only
    lower that accepted score further. The trace is therefore monotonic even
    when its residual representation changes dimension across hypotheses.
    """
    if not problems or max_steps < 1:
        raise ValueError("nonempty hypotheses and positive step budget required")
    point = np.asarray(start, float).copy()
    if point.shape != (2,) or not np.isfinite(point).all():
        raise ValueError("finite two-coordinate start required")
    for p in problems:
        if np.any(point < p.lower) or np.any(point > p.upper):
            raise ValueError("start outside regional search box")
    evaluations = 0

    def choose(x, incumbent=None):
        nonlocal evaluations
        scores = [score(p, x) for p in problems]
        evaluations += len(scores)
        if not np.isfinite(scores).all():
            raise ValueError("nonfinite hypothesis objective")
        best = int(np.argmin(scores))
        if incumbent is not None and scores[incumbent] <= scores[best] + 1e-7:
            best = incumbent
        return best, scores

    active, scores = choose(point)
    trace = [dict(step=0, point=point.copy(), mode=active, score=scores[active],
                  hypothesis_scores=scores)]
    switches, stopped = [], "step_budget"
    for step in range(1, max_steps + 1):
        previous, previous_score = point.copy(), scores[active]
        p = problems[active]
        fit = bounded_gauss_newton(p.residual, point, p.lower, p.upper, iterations=1)
        evaluations += fit["evaluations"]
        if len(fit["history"]) < 2:
            stopped = fit["stopped"]
            break
        point = np.asarray(fit["parameters"])
        new, scores = choose(point, active)
        if scores[new] > previous_score + 1e-6:
            raise ValueError("joint descent objective increased")
        if new != active:
            switches.append(dict(step=step, point=point.copy(), old_mode=active,
                                 new_mode=new, improvement=scores[active] - scores[new]))
        distance, improvement = np.linalg.norm(point - previous), previous_score - scores[new]
        active = new
        trace.append(dict(step=step, point=point.copy(), mode=active, score=scores[active],
                          hypothesis_scores=scores))
        if distance < 1e-4 and improvement < 1e-5:
            stopped = "small_step_and_improvement"
            break
    return dict(parameters=point, score=scores[active], final_mode=active,
                trace=trace, switches=switches, stopped=stopped,
                steps=len(trace) - 1, evaluations=evaluations, max_steps=max_steps)


def worker(case, start_id):
    path = OUTPUT / case / f"start_{start_id:02d}.json"
    if path.exists():
        return
    guard = JointReadGuard(CLEAN)
    guard.install()
    mark = time.monotonic()
    scan, sigma = load_scan(case)
    nodes, bindings = hypothesis_bank(scan, sigma)
    arms = {}
    for arm in ARMS:
        problems = [factory(scan, n, sigma, "normal", arm == "fitted_c") for n in nodes]
        result = descend(problems, STARTS[start_id])
        p = problems[result["final_mode"]]
        x = result["parameters"]
        calculated = p.calculate(x)
        state = p.state(x)
        fit = dict(rows=p.rows, state=state, aliases=list(p.alias), east_north_km=x,
                   fits=[dict(parameters=x, score=result["score"])])
        metrics = actual_metrics(p, fit, arm, x)
        for event in result["switches"]:
            event.update(assignment_changes(nodes[event["old_mode"]], nodes[event["new_mode"]]))
        arms[arm] = dict(result, state=state, aliases=list(p.alias), rows=p.rows,
                         phase_reference_s=p.reference,
                         residual_rms_hz=float(np.sqrt(np.mean(
                             calculated["conditional_residual_hz"] ** 2))),
                         associated_points=metrics["accepted_points"],
                         associated_fragments=metrics["accepted_tracks"],
                         associated_native_rms_hz=metrics["accepted_native_rms_hz"],
                         tracks=metrics["tracks"],
                         nuisance_converged=calculated.get("converged"))
    result = dict(case=case, start_id=start_id, start_east_north_km=STARTS[start_id], arms=arms,
                  hypotheses=[dict(id=i, source_start_id=n["source_start_id"],
                                   signature=signature(n))
                              for i, n in enumerate(nodes)],
                  discovery_bindings=bindings, input_audit=scan.inference_input_audit,
                  actual_inputs_read=sorted(guard.read_paths),
                  GPS_or_following_TLE_used=False, all_inherited_nuisance_state_discarded=True,
                  phase_reference="common zero for all hypotheses and both c arms",
                  center=CENTER, box_width_km=25, grid_radius_km=10, grid_step_km=2,
                  curved_points=sum(len(scan.tracks[i]["times"]) for i in scan.curved),
                  sigma_hz=sigma, max_steps=MAX_STEPS, status="complete",
                  seconds=time.monotonic() - mark)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    write(temporary, result)
    temporary.replace(path)
    print(case, start_id, result["seconds"], flush=True)


def run(workers):
    OUTPUT.mkdir(parents=True, exist_ok=True)
    write(OUTPUT / "protocol.json", dict(
        cases=CASES, starts=STARTS, starts_per_scan=len(STARTS), arms=ARMS,
        model="graph tracks, normal shared orbit/radio covariance",
        algorithm="lower-envelope descent; rescore all hypotheses after every accepted step",
        hypothesis_origin="union of 13 same-scan cold radio discoveries; discard all fitted state",
        hypothesis_limitation=("finite whole-assignment hypotheses, "
                               "not exhaustive catalogue/fragment combinations"),
        common_zero_phase_reference=True, matched_candidates_priors_starts_and_budgets=True,
        GPS_or_following_TLE_used=False, center=CENTER, box_width_km=25,
        max_steps=MAX_STEPS,
        source_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()))

    def job(case, index):
        log = OUTPUT / "logs" / f"{case}_{index:02d}.log"
        log.parent.mkdir(exist_ok=True)
        with log.open("w") as handle:
            done = subprocess.run([sys.executable, __file__, "--case", case,
                                   "--start-id", str(index)], stdout=handle,
                                  stderr=subprocess.STDOUT, check=False,
                                  env=dict(os.environ, OPENBLAS_NUM_THREADS="1",
                                           OMP_NUM_THREADS="1", PYTHONPATH="src:tools"))
        return dict(case=case, start_id=index, returncode=done.returncode, log=str(log))

    # Round robin over scans so each receives early coverage.
    with ThreadPoolExecutor(max_workers=workers) as pool:
        pending = [pool.submit(job, c, i) for i in range(len(STARTS)) for c in CASES]
        results = []
        for future in as_completed(pending):
            result = future.result()
            results.append(result)
            print(json.dumps(dict(completed=len(results), total=len(pending), **result)),
                  flush=True)
            write(OUTPUT / "progress.json", dict(completed=len(results), total=len(pending),
                                                failures=[r for r in results if r["returncode"]]))
    if any(r["returncode"] for r in results):
        raise RuntimeError("joint descent workers failed; inspect progress/logs")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", choices=CASES)
    parser.add_argument("--start-id", type=int, choices=range(len(STARTS)))
    parser.add_argument("--workers", type=int, default=20)
    args = parser.parse_args()
    if args.case is not None:
        if args.start_id is None:
            parser.error("--case requires --start-id")
        worker(args.case, args.start_id)
    else:
        run(args.workers)
