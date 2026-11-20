"""End an orbit refresh after the receiver position and every orbit shift settle."""

import json
import sys
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch

import numpy as np

from tools.pipeline_eval.__main__ import save_json
from tools.pipeline_eval.variants import orbit_projector, v5_lean, v5_secant_fit

METHOD = "v5_stable_phase"
BOUNDARY = "Stored native GLRT to compact v5 with converged initial and repair phase fits"
PHASE_SECONDS = 0.01
POSITION_KM = 0.001


def refresh(build, fit, reference, *, rounds, iterations, start=(0.0, 0.0)):
    if rounds < 1 or iterations < 1:
        raise ValueError("positive phase and position budgets required")
    anchor = np.asarray(start, dtype=float)
    history = []
    for epoch in range(rounds):
        model = build(reference)
        result = fit(model, anchor, iterations=iterations)
        after = np.asarray(result["parameters"], dtype=float)
        phase = model.state(after)["phases"][model.labels]
        raw_change = float(np.max(np.abs(phase - reference)))
        movement = float(np.linalg.norm(after - anchor))
        history.append(
            dict(
                epoch=epoch,
                fit=result,
                phase_reference=reference.copy(),
                posterior_phase_s=phase,
                max_reference_change_s=raw_change,
                movement_km=movement,
            )
        )
        if epoch and raw_change <= PHASE_SECONDS and movement <= POSITION_KM:
            break
        reference = np.clip(phase, -15, 15)
        anchor = after
    return model, result, history


def policies(receipts):
    from leo.analysis.localization_v3 import position, retained_position

    def record(stage, arm, history, requested):
        receipts.append(
            dict(
                stage=stage,
                arm=arm,
                requested=requested,
                performed=len(history),
                last_move_km=history[-1]["movement_km"],
                last_phase_change_s=history[-1]["max_reference_change_s"],
            )
        )

    def initial(scan, sigma, node, arm, *, rounds=5, iterations=48):
        if arm not in {"c0", "fitted_c"}:
            raise ValueError("unknown calibration arm")
        labels = {row["candidate_index"] for row in node["seed"]["rows"]}

        def build(reference):
            return position.NormalPosition(
                scan, node, sigma, arm == "fitted_c", reference=reference
            )

        p, r, history = refresh(
            build, position.fit, np.zeros(len(labels)), rounds=rounds, iterations=iterations
        )
        record("initial", arm, history, rounds)
        return p, r, history

    def repair(scan, node, arm, kind, keep, *, rounds=5, iterations=48):
        if kind not in {"unit", "phase3", "causal"}:
            raise ValueError("unsupported repair prior")
        labels = sorted({row["candidate_index"] for row in node["seed"]["rows"]})
        widths, receipt = retained_position.phase_widths(scan, labels)

        def build(reference):
            p = retained_position.NormalPosition(
                scan, node, scan.radio_sigma_hz, arm == "fitted_c", reference=reference, keep=keep
            )
            if kind == "phase3":
                p.phase_sigma = np.full(len(labels), 3.0)
            if kind == "causal":
                p.phase_sigma = widths
            return p

        p, r, history = refresh(
            build,
            retained_position.fit,
            np.zeros(len(labels)),
            rounds=rounds,
            iterations=iterations,
        )
        record("repair", arm, history, rounds)
        return p, r, [h["max_reference_change_s"] for h in history], receipt

    return initial, repair


def worker(request, result, library):
    from leo.analysis.localization_v3 import conservative_recovery, position

    receipts = []
    initial, repair = policies(receipts)
    with ExitStack() as stack:
        stack.enter_context(patch.object(position, "refreshed", initial))
        stack.enter_context(patch.object(conservative_recovery, "repaired_fit", repair))
        v5_secant_fit.worker(request, result, library, "secant")
    value = json.loads(Path(result).read_bytes())
    value["boundary"] = BOUNDARY
    value["metrics"]["phase_termination"] = receipts
    save_json(Path(result), value)


def run(case, work):
    library = Path(work) / "orbit_projector.so"
    library.parent.mkdir(parents=True, exist_ok=True)
    orbit_projector.compile_kernel(library)
    return v5_lean.run_bound_worker(case, work, Path(__file__), worker_args=(str(library),))


if __name__ == "__main__":
    worker(*sys.argv[1:])
