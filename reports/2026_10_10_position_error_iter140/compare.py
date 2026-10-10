"""Unchanged phase physics, four common fitted-derived starts, no truth choice."""

import runpy
import time
from pathlib import Path

import numpy as np

REPORTS = Path(__file__).resolve().parent.parent
MEASUREMENT = runpy.run_path(str(REPORTS / "2026_10_10_position_error_iter133/measurement.py"))
PHASE = runpy.run_path(str(REPORTS / "2026_10_10_position_error_iter130/objective.py"))
ARMS = ("fitted-c", "zero-c")
VARIANTS = ("timestamp", "phase")


def compare(model, projection, run_attempt):
    archives = {a: projection["operational"][a]["fit"] for a in ARMS}
    selected = archives["fitted-c"]
    vector, clock = np.asarray(selected["vector"]), np.asarray(selected["clock_coefficients"])
    original_value = float(model.evaluate_joint(vector, clock)[0])
    if not np.isfinite(original_value) or abs(original_value - selected["objective"]) > 1e-6:
        raise ValueError("Fitted-selected model parity failed before fitting")
    if model.slope_slice.stop != len(clock) - 2:
        raise ValueError("Unreviewed RF-time layout")
    starts = MEASUREMENT["shared_starts"](
        vector,
        clock,
        rf_clock_columns=[len(clock) - 2, len(clock) - 1],
        fixed_rf_drift=model.fixed_rf_drift,
    )
    attempts = {}
    for variant in VARIANTS:
        attempts[variant] = {}
        for arm in ARMS:
            begun = time.monotonic()
            try:
                cloned = MEASUREMENT["clone_measurement_model"](
                    model, model.observations.measured_hz
                )
                candidate = PHASE["convert"](cloned) if variant == "phase" else cloned
                seed = starts["original", arm]
                fit = run_attempt(
                    candidate, seed["vector"].copy(), seed["clock_coefficients"].copy(), arm
                )
                attempts[variant][arm] = dict(
                    status="complete", qualified=bool(fit["converged"]), fit=fit
                )
            except Exception as exc:
                attempts[variant][arm] = dict(status="failed", qualified=False, error=repr(exc))
            attempts[variant][arm]["elapsed_s"] = time.monotonic() - begun
    integrity = []
    try:
        value = float(model.evaluate_joint(vector, clock)[0])
        if not np.isfinite(value) or abs(value - selected["objective"]) > 1e-6:
            integrity.append("Fitted-selected ordinary model changed")
    except Exception as exc:
        integrity.append(repr(exc))
    return dict(
        status="model-integrity-failed"
        if integrity
        else "complete"
        if all(a["status"] == "complete" for rows in attempts.values() for a in rows.values())
        else "attempt-failed",
        attempts=attempts,
        archive=archives,
        integrity_failures=integrity,
        archive_role="Latest107 candidate; independent zero-c model historical comparator only",
        initialization="All four fitted-derived starts, except zero-c RF locks",
        selection="None; timestamp and phase reported separately",
    )
