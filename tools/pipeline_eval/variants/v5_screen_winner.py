"""Screen initial satellite assignments at two orbit updates and finish the winner at five."""

import json
import sys
from pathlib import Path
from time import process_time
from unittest.mock import patch

import numpy as np

from tools.pipeline_eval.variants import orbit_projector, v5_core, v5_lean

SCREEN_ROUNDS = 2
TOTAL_ROUNDS = 5
INNER_ITERATIONS = 48
MODES = ("reference", "secant")
BOUNDARY = "Complete native GLRT through compact v5 with early assignment screening"


def screen_nodes(scan, nodes, metrics):
    from leo.analysis.localization_v3 import position
    from leo.analysis.localization_v3.acceptance import actual_metrics

    if not nodes:
        raise ValueError("initial screening requires a ranked satellite assignment")
    started = process_time()
    sigma = scan.radio_sigma_hz
    screens = []
    for node in nodes:
        model, fit, history = position.refreshed(
            scan, sigma, node, "c0", rounds=SCREEN_ROUNDS, iterations=INNER_ITERATIONS
        )
        # These are the two inputs carried into the next original refresh iteration.
        anchor = np.array(fit["parameters"])
        reference = np.clip(history[-1]["posterior_phase_s"], -15, 15)
        screens.append((float(fit["score"]), anchor, reference))
        del model, fit, history

    scores = [score if np.isfinite(score) else None for score, _, _ in screens]
    fallback = None in scores
    finish = TOTAL_ROUNDS * len(nodes) if fallback else TOTAL_ROUNDS - SCREEN_ROUNDS
    metrics.update(
        ranks=list(range(len(nodes))),
        screen_c0_scores=scores,
        winning_rank=None,
        completed_c0_score=None,
        early_fits=SCREEN_ROUNDS * len(nodes),
        finish_fits=finish,
        initial_phase_fits=SCREEN_ROUNDS * len(nodes) + finish,
        fallback=fallback,
    )
    if fallback:
        answer = v5_core.fit_initial_nodes(scan, nodes)
    else:
        winner = min(range(len(nodes)), key=scores.__getitem__)
        _, anchor, reference = screens[winner]
        node = nodes[winner]
        for _ in range(finish):
            model = position.NormalPosition(scan, node, sigma, False, reference=reference)
            fit = position.fit(model, anchor, iterations=INNER_ITERATIONS)
            anchor = np.array(fit["parameters"])
            state = model.state(anchor)
            reference = np.clip(state["phases"][model.labels], -15, 15)
        checkpoint = dict(
            rows=model.rows, state=state, aliases=model.alias, east_north_km=anchor, fits=[fit]
        )
        gate = actual_metrics(model, checkpoint, "c0", anchor)
        choice = dict(hypothesis=0, node=node, arms={"c0": {"metrics": gate}})
        answer = {"choices": [choice], "selected_hypothesis": 0}, len(nodes)
        metrics.update(winning_rank=winner, completed_c0_score=float(fit["score"]))
    metrics["initial_screen_cpu_s"] = process_time() - started
    return answer


def worker(request, output, library, mode):
    from leo.analysis.localization_v3 import position

    from tools.pipeline_eval.__main__ import save_json

    if mode not in MODES:
        raise ValueError("unknown assignment-screening optimizer")
    optimizer = position.bounded_gauss_newton
    if mode == "secant":
        from tools.pipeline_eval.variants.v5_secant_fit import bounded_secant

        optimizer = bounded_secant
    work = {"calls": 0, "evaluations": 0}
    metrics = {}

    def solve(*args, **kwargs):
        result = optimizer(*args, **kwargs)
        work["calls"] += 1
        work["evaluations"] += result["evaluations"]
        return result

    def select(scan):
        return screen_nodes(scan, v5_core.ranked_initial_nodes(scan)[:3], metrics)

    with patch.object(position, "bounded_gauss_newton", solve):
        orbit_projector.worker(request, output, library, select_initial=select)
    output = Path(output)
    result = json.loads(output.read_bytes())
    result["boundary"] = BOUNDARY
    result["metrics"].update(mode=mode, initial_screen=metrics, position_optimizer=work)
    save_json(output, result)


def run(case, work_dir, mode="reference"):
    if mode not in MODES:
        raise ValueError("unknown assignment-screening optimizer")
    lib = Path(work_dir) / "orbit_projector.so"
    lib.parent.mkdir(parents=True, exist_ok=True)
    orbit_projector.compile_kernel(lib)
    return v5_lean.run_bound_worker(case, work_dir, Path(__file__), worker_args=(str(lib), mode))


if __name__ == "__main__":
    worker(*sys.argv[1:])
