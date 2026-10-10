"""Four matched attempts; acquisition-only pairing precedes either c arm."""

import time

import numpy as np

ARMS = ("fitted-c", "zero-c")
VARIANTS = ("control", "rho25")


def compare(
    model,
    archive,
    support,
    *,
    physics,
    pair_rows,
    shared_starts,
    clone_model,
    phase_convert,
    paired_convert,
    phase_predict,
    timestamp_predict,
    emission,
    run_attempt,
    progress=None,
):
    progress = {} if progress is None else progress
    progress["support"] = support
    if physics not in ("timestamp", "phase"):
        raise ValueError("Explicit globally frozen physics required")
    pairing = pair_rows(support["rows"])
    progress["pairing"] = pairing
    if pairing["observations"] != len(model.observations.times_s):
        raise ValueError("Support membership differs from original rows")
    pairs = np.asarray(pairing["pairs"], dtype=int).reshape(-1, 2)
    endpoints = archive["stages"]["B7"]
    parity = {}
    progress["archive_parity"] = parity
    for arm in ARMS:
        saved = endpoints[arm]
        value = float(
            model.evaluate_joint(
                np.asarray(saved["vector"]), np.asarray(saved["clock_coefficients"])
            )[0]
        )
        if not np.isfinite(value) or abs(value - saved["objective"]) > 1e-6:
            raise ValueError("Ordinary archive parity failed: " + arm)
        parity[arm] = value - saved["objective"]
    saved = endpoints["fitted-c"]
    clock = np.asarray(saved["clock_coefficients"])
    if model.slope_slice.stop != len(clock) - 2:
        raise ValueError("Unreviewed RF-time column layout")
    starts = shared_starts(
        saved["vector"],
        clock,
        rf_clock_columns=[len(clock) - 2, len(clock) - 1],
        fixed_rf_drift=model.fixed_rf_drift,
    )
    attempts = {}
    progress["attempts"] = attempts
    for variant in VARIANTS:
        attempts[variant] = {}
        for arm in ARMS:
            begun = time.monotonic()
            try:
                control = clone_model(model, model.observations.measured_hz)
                if physics == "phase":
                    control = phase_convert(control)
                objective = (
                    control
                    if variant == "control"
                    else paired_convert(
                        control,
                        pairs,
                        0.25,
                        prediction_provider=phase_predict
                        if physics == "phase"
                        else timestamp_predict,
                        emission_provider=emission,
                    )
                )
                seed = starts["original", arm]
                fit = run_attempt(
                    objective, seed["vector"].copy(), seed["clock_coefficients"].copy(), arm
                )
                attempts[variant][arm] = dict(
                    status="complete", qualified=bool(fit["converged"]), fit=fit
                )
            except Exception as exc:
                attempts[variant][arm] = dict(status="failed", qualified=False, error=repr(exc))
            attempts[variant][arm]["elapsed_s"] = time.monotonic() - begun
    integrity = []
    for arm in ARMS:
        try:
            saved = endpoints[arm]
            value = float(
                model.evaluate_joint(
                    np.asarray(saved["vector"]), np.asarray(saved["clock_coefficients"])
                )[0]
            )
            if not np.isfinite(value) or abs(value - saved["objective"]) > 1e-6:
                integrity.append("Original model changed: " + arm)
        except Exception as exc:
            integrity.append(repr(exc))
    return dict(
        status="model-integrity-failed"
        if integrity
        else "complete"
        if all(a["status"] == "complete" for values in attempts.values() for a in values.values())
        else "attempt-failed",
        attempts=attempts,
        archive=endpoints,
        archive_parity=parity,
        integrity_failures=integrity,
        pairing=pairing,
        support=support,
        physics=physics,
        initialization="same fitted-derived start with c0 RF locks",
        selection="none",
    )
