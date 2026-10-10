"""Four same-start fits of immutable timestamp/phase models; no truth selection."""

import runpy
import time
from pathlib import Path

import numpy as np

REPORTS = Path(__file__).resolve().parent.parent
MEASUREMENT = runpy.run_path(str(REPORTS / "2026_10_10_position_error_iter133/measurement.py"))
PHASE = runpy.run_path(str(REPORTS / "2026_10_10_position_error_iter130/objective.py"))
ARMS = ("fitted-c", "zero-c")
VARIANTS = ("timestamp", "phase")


def compare(model, archive, run_attempt):
    endpoints = archive["stages"]["B7"]
    parity = {}
    for arm in ARMS:
        saved = endpoints[arm]
        value = float(
            model.evaluate_joint(
                np.asarray(saved["vector"]), np.asarray(saved["clock_coefficients"])
            )[0]
        )
        if not np.isfinite(value) or abs(value - saved["objective"]) > 1e-6:
            raise ValueError("original archived objective mismatch: " + arm)
        parity[arm] = value - saved["objective"]
    saved = endpoints["fitted-c"]
    clock = np.asarray(saved["clock_coefficients"])
    if model.slope_slice.stop != len(clock) - 2:
        raise ValueError("unreviewed RF-time layout")
    starts = MEASUREMENT["shared_starts"](
        saved["vector"],
        clock,
        rf_clock_columns=[len(clock) - 2, len(clock) - 1],
        fixed_rf_drift=model.fixed_rf_drift,
    )
    models = {}
    for name in VARIANTS:
        for arm in ARMS:
            cloned = MEASUREMENT["clone_measurement_model"](model, model.observations.measured_hz)
            models[name, arm] = PHASE["convert"](cloned) if name == "phase" else cloned
    attempts = {}
    for name in VARIANTS:
        attempts[name] = {}
        for arm in ARMS:
            seed = starts["original", arm]
            begun = time.monotonic()
            try:
                fit = run_attempt(
                    models[name, arm], seed["vector"].copy(), seed["clock_coefficients"].copy(), arm
                )
                attempts[name][arm] = dict(
                    status="complete", qualified=bool(fit["converged"]), fit=fit
                )
            except Exception as exc:
                attempts[name][arm] = dict(status="failed", qualified=False, error=repr(exc))
            attempts[name][arm]["elapsed_s"] = time.monotonic() - begun
    integrity = []
    for arm in ARMS:
        saved = endpoints[arm]
        try:
            value = float(
                model.evaluate_joint(
                    np.asarray(saved["vector"]), np.asarray(saved["clock_coefficients"])
                )[0]
            )
            if not np.isfinite(value) or abs(value - saved["objective"]) > 1e-6:
                integrity.append("original model changed: " + arm)
        except Exception as exc:
            integrity.append(repr(exc))
    return dict(
        status="model-integrity-failed"
        if integrity
        else "complete"
        if all(a["status"] == "complete" for arms in attempts.values() for a in arms.values())
        else "attempt-failed",
        attempts=attempts,
        archive=endpoints,
        archive_parity=parity,
        integrity_failures=integrity,
        initialization="same fitted-derived vector/clock for all four fits, except c0 RF locks",
        selection="none; timestamp and phase reported separately",
    )
