"""Experimental Model A: learn high offsets with low satellite timings fixed.

The original low and final models remain unchanged. Only the conditional high
fit loses its timing freedom. This is a falsifiable training-only control, not
a new hardware calibration claim or a validated localization improvement.
"""

import time
from contextlib import suppress

import numpy as np
from scipy.optimize import minimize

from leo.analysis.channel_group_calibration import fit_group_calibration
from leo.analysis.sequential_group_calibration import (
    SequentialHighObjective,
    fit_sequential_path,
)


def fit_timing_locked_high(model, vector, nuisance, *, seconds=20.0, iterations=600):
    """Fit only supported receiver offsets; independently audit their box KKT.

    The supplied physical vector is never clipped or changed. Its common and
    relative satellite timings must already be feasible on the high rows.
    Stationarity is conditional on the complete fixed vector, including timing;
    it is deliberately different from the original timing-free high certificate.
    """
    if not isinstance(model, SequentialHighObjective):
        raise ValueError("original sequential high objective required")
    if (
        not np.isfinite(seconds)
        or not 0 < seconds <= 20
        or not isinstance(iterations, int)
        or not 1 <= iterations <= 600
    ):
        raise ValueError("high control requires at most 20 seconds and 600 iterations")
    vector = np.asarray(vector, float).copy()
    nuisance = np.asarray(nuisance, float).copy()
    if (
        vector.shape != (model.size,)
        or not np.isfinite(vector).all()
        or not np.array_equal(vector[2:7], np.zeros(5))
        or nuisance.shape != model.initial_nuisance.shape
        or not np.isfinite(nuisance).all()
        or model.clock_count
        or model.drift_count
        or model.group_clock_count
    ):
        raise ValueError("fixed physical vector and receiver-offset-only layout required")
    scales, limits = model.group_scales, model.group_limits
    if not len(scales) or np.any(abs(nuisance) > limits):
        raise ValueError("supported high offset seed within original alias bounds required")
    obs = model.observations
    coverage_min = float(model.bank.nodes_s[0] - obs.times_s.min())
    coverage_max = float(model.bank.nodes_s[-1] - obs.times_s.max())
    minimum, maximum = max(-20.0, coverage_min), min(20.0, coverage_max)
    shifts = vector[7] + model.basis @ vector[8:]
    if (
        not coverage_min < minimum < 0 < maximum < coverage_max
        or abs(vector[7]) > 10
        or np.any(shifts < minimum - 1e-7)
        or np.any(shifts > maximum + 1e-7)
        or np.linalg.norm(vector[:2]) > model.prior.radius_km + 1e-9
    ):
        raise ValueError("low timing/geography is infeasible on high rows; no clipping allowed")
    slack = float(
        min(
            np.min(shifts - minimum),
            np.min(maximum - shifts),
            model.prior.radius_km**2 - vector[:2] @ vector[:2],
        )
    )
    begun, records = time.monotonic(), []

    class Deadline(Exception):
        pass

    def evaluate(z):
        if time.monotonic() - begun >= seconds:
            raise Deadline()
        offsets = z * scales
        value, _, gradient, _ = model.evaluate_joint(vector, offsets)
        if not np.isfinite(value) or not np.isfinite(gradient).all():
            raise ValueError("nonfinite high conditional objective or gradient")
        if np.all(abs(offsets) <= limits + 1e-7):
            derivative = scales * gradient.copy()
            derivative[(offsets <= -limits + 1e-7) & (derivative >= 0)] = 0
            derivative[(offsets >= limits - 1e-7) & (derivative <= 0)] = 0
            records.append(
                (
                    float(value),
                    offsets.copy(),
                    float(np.max(abs(derivative), initial=0)),
                )
            )
        return float(value), scales * gradient

    solver = None
    with suppress(Deadline):
        solver = minimize(
            evaluate,
            nuisance / scales,
            jac=True,
            method="SLSQP",
            bounds=list(zip(-limits / scales, limits / scales, strict=True)),
            options={"maxiter": iterations, "ftol": 1e-11},
        )
    if not records:
        raise TimeoutError("no feasible high-offset conditional evaluation")
    stationary = [row for row in records if row[2] <= 0.001]
    value, offsets, kkt = min(stationary or records, key=lambda row: row[0])
    _, _, _, terms = model.evaluate_joint(vector, offsets)
    mass = float(terms.responsibilities.sum())
    return dict(
        vector=vector,
        nuisance=offsets,
        group_receivers=list(model.frame.receivers),
        training_high_fractions=None,
        group_offsets_hz=offsets,
        group_drifts_hz_s=np.empty(0),
        group_clock_coefficients=np.empty(0),
        clock_coefficients=np.empty(0),
        training_time_center_s=model.group_time_center_s,
        training_rf_center_hz=obs.rf_center_hz,
        objective=value,
        likelihood_nll=float(terms.nll),
        posterior_rms_hz=(
            float(np.sqrt(np.sum(terms.responsibilities * terms.residual_hz**2) / mass))
            if mass > 0
            else None
        ),
        signal_windows=mass,
        stationarity=kkt,
        converged=kkt <= 0.001,
        boundary=slack < 1e-6,
        physical_constraints_minimum=slack,
        elapsed_s=time.monotonic() - begun,
        evaluations=len(records),
        solver_success=bool(solver is not None and solver.success),
        group_prior_penalty=0.5 * float(offsets @ model.group_precision @ offsets),
        stationarity_scope="receiver-offsets-only; low-position-correction-timing-fixed",
        fixed_timing=True,
        fixed_timing_source="own stationary low-stage fit",
        fitted_c=True,
    )


def fit_model_a_timing_locked_path(
    low_model,
    high_base,
    all_base,
    low_seed,
    high_seed,
    all_seed,
    *,
    seconds=20.0,
    iterations=600,
    stage_sink=None,
    **options,
):
    """Run one own-path control; preserve the original low/final fit and selector.

    A receipt sink can seal each stage with its actual input seed/options. It
    receives no held observations or reference positions. The caller retains
    failed paths and selects complete paths by final training objective only.
    """
    if "arm" in options or "stage_fit" in options:
        raise ValueError("control is fitted-c only with its own high-stage dispatcher")
    if (
        not np.isfinite(seconds)
        or not 0 < seconds <= 20
        or not isinstance(iterations, int)
        or not 1 <= iterations <= 600
    ):
        raise ValueError("control requires at most 20 seconds and 600 iterations per stage")
    low_fit = None

    def stage_fit(stage, model, vector, nuisance, fit_options):
        nonlocal low_fit
        vector = np.asarray(vector, float).copy()
        if stage == "high":
            if low_fit is None or not low_fit["converged"]:
                raise ValueError("high control requires its own stationary low fit")
            vector[7:] = low_fit["vector"][7:]
            fit = fit_timing_locked_high(
                model,
                vector,
                nuisance,
                seconds=seconds,
                iterations=iterations,
            )
        else:
            fit = fit_group_calibration(model, vector, nuisance, **fit_options)
            if stage == "low":
                low_fit = fit
        if stage_sink is not None:
            stage_sink(stage, vector.copy(), nuisance, dict(fit_options), fit)
        return fit

    result = fit_sequential_path(
        low_model,
        high_base,
        all_base,
        low_seed,
        high_seed,
        all_seed,
        arm="fitted-c",
        seconds=seconds,
        iterations=iterations,
        stage_fit=stage_fit,
        **options,
    )
    result["experimental_policy"] = "model-a-low-timing-locked-high-v1"
    return result
