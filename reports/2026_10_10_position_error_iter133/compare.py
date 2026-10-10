"""Six matched final fits, without reference fields or cross-variant selection."""

import time

import numpy as np
from measurement import ARMS, VARIANTS, clone_measurement_model, shared_starts, substitute


def compare(model, archive, rows, run_attempt):
    """Caller supplies the frozen clean model, original IQ receipts and fitter.

    Validate every measurement set before any optimizer call. Failed fits remain
    explicit and cannot silently replace another arm's start or observations.
    """
    begun = time.monotonic()
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

    measurements = {
        name: substitute(model.observations.window_ids, model.observations.measured_hz, rows, name)
        for name in VARIANTS
    }
    models = {
        name: clone_measurement_model(model, value["measured_hz"])
        for name, value in measurements.items()
    }
    saved = endpoints["fitted-c"]
    clock = np.asarray(saved["clock_coefficients"])
    # The audited SatelliteCorrection layout places both RF-time terms last.
    if model.slope_slice.stop != len(clock) - 2:
        raise ValueError("unreviewed RF-time nuisance layout")
    starts = shared_starts(
        saved["vector"],
        clock,
        rf_clock_columns=[len(clock) - 2, len(clock) - 1],
        fixed_rf_drift=model.fixed_rf_drift,
    )
    attempts = {}
    for name in VARIANTS:
        attempts[name] = {}
        for arm in ARMS:
            seed = starts[(name, arm)]
            started = time.monotonic()
            try:
                fit = run_attempt(
                    models[name], seed["vector"].copy(), seed["clock_coefficients"].copy(), arm
                )
                attempts[name][arm] = dict(
                    status="complete",
                    qualified=bool(fit["converged"]),
                    fit=fit,
                )
            except Exception as error:
                attempts[name][arm] = dict(status="failed", error=repr(error), qualified=False)
            attempts[name][arm]["elapsed_s"] = time.monotonic() - started
    # Shared arrays must not allow any candidate fitting to corrupt the control.
    integrity_failures = []
    for arm in ARMS:
        saved = endpoints[arm]
        try:
            value = float(
                model.evaluate_joint(
                    np.asarray(saved["vector"]), np.asarray(saved["clock_coefficients"])
                )[0]
            )
            if not np.isfinite(value) or abs(value - saved["objective"]) > 1e-6:
                integrity_failures.append("original model changed during candidate fitting: " + arm)
        except Exception as error:
            integrity_failures.append(f"original model verification failed {arm}: {error!r}")
    return dict(
        status="model-integrity-failed"
        if integrity_failures
        else "complete"
        if all(a["status"] == "complete" for arms in attempts.values() for a in arms.values())
        else "attempt-failed",
        integrity_failures=integrity_failures,
        archive_parity=parity,
        archive=endpoints,
        attempts=attempts,
        measurement_changes={
            name: {key: values[key] for key in ("circular_delta_hz", "representation_wraps")}
            for name, values in measurements.items()
        },
        elapsed_s=time.monotonic() - begun,
        initialization="same ordinary fitted-c vector/clock for six fits, with c=0 locks",
        selection="none; each measurement model reported separately",
    )
