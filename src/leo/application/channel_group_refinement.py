"""Matched channel-view refinement from sealed cold training discovery."""

import time

import numpy as np

from leo.analysis.channel_group_calibration import (
    GroupCalibrationObjective,
    fit_group_calibration,
    project_calibration_seed,
)
from leo.analysis.frozen_group_calibration import freeze_group_calibration
from leo.analysis.frozen_position_prediction import (
    freeze_group_position,
    score_frozen_group_position,
)
from leo.analysis.hard60_joint_clock import JointClockObjective
from leo.analysis.hard60_score import Hard60Objective
from leo.analysis.regional_position_score import zero_sum_basis
from leo.application.channel_group_discovery import DiscoverySliceExpired
from leo.application.hard60_runner import HARD60_SCORE


def objective(
    inputs, bank, prior, nodes, *, differential_clock=False, common_clock=True, likelihood_port=None
):
    if likelihood_port is not None and not common_clock:
        raise ValueError("Declared frequency likelihood requires the explicit joint clock model")
    base = Hard60Objective(inputs.observations, bank, prior, HARD60_SCORE)
    if common_clock:
        base = JointClockObjective(
            base, nodes, np.zeros((2, len(nodes))), 4, likelihood_port=likelihood_port
        )
    return GroupCalibrationObjective(
        base,
        inputs.observations.channel >= 5,
        group_drift_sigma_hz_s=2 if differential_clock else None,
        group_clock=differential_clock,
    )


def carried_seed(
    row,
    selected_rows,
    target_model,
    prepared,
    bank,
    prior,
    nodes,
    early_clock,
    *,
    nearest_timings=False,
):
    """Combine trained physical half corrections; preserve inferred satellite timings."""
    source_bank = bank.select(list(row["satellite_indices"]))
    states = {}
    for view, fit in row["fits"].items():
        if fit["converged"]:
            model = objective(prepared[view], source_bank, prior, nodes, common_clock=early_clock)
            states[view] = freeze_group_calibration(model, fit)
    if not states:
        raise ValueError("stationary cold training correction required")
    target = target_model.observations
    fallback = states.get("all", next(iter(states.values())))
    low, high = states.get("low", fallback), states.get("high", fallback)
    args = (target.times_s, target.rf_hz, target.receiver, target.channel >= 5)
    correction = np.where(target.channel >= 5, high.predict(*args), low.predict(*args))
    projection = project_calibration_seed(target_model, correction)
    timings = {int(number): [] for number in target_model.bank.numbers}
    # Prefer this point's all-view inferred timings. Missing candidates retain
    # their first available timing in the declared start/view order, never a
    # held-data inference. No clock model needs reconstruction for this gauge.
    other_rows = [other for other in selected_rows if other is not row]
    if nearest_timings:
        other_rows.sort(
            key=lambda other: (
                (other["east_km"] - row["east_km"]) ** 2
                + (other["north_km"] - row["north_km"]) ** 2,
                other["east_km"],
                other["north_km"],
            )
        )
    for source_row in [row, *other_rows]:
        for view in ("all", "low", "high"):
            fit = source_row["fits"].get(view, {})
            if not fit.get("converged"):
                continue
            vector = np.asarray(fit["vector"])
            numbers = bank.numbers[list(source_row["satellite_indices"])]
            if vector.shape != (7 + len(numbers),):
                raise ValueError("Cold timing vector differs from its candidate bank")
            shifts = vector[7] + zero_sum_basis(len(numbers)) @ vector[8:]
            for number, shift in zip(numbers, shifts, strict=True):
                if not timings[int(number)]:
                    timings[int(number)].append(float(shift))
        if all(timings.values()):
            break
    if any(not values for values in timings.values()):
        raise ValueError("candidate lacks stationary cold training timing")
    shifts = np.array([np.median(timings[int(number)]) for number in target_model.bank.numbers])
    shifts -= shifts.mean() - np.clip(shifts.mean(), -9.9, 9.9)
    shifts *= min(1.0, 19.9 / max(19.9, float(abs(shifts).max())))
    coefficients = projection["coefficients"]
    vector = np.r_[
        row["east_km"],
        row["north_km"],
        coefficients[:5],
        shifts.mean(),
        target_model.basis.T @ (shifts - shifts.mean()),
    ]
    return dict(vector=vector, nuisance=coefficients[5:], projection_rms_hz=projection["rms_hz"])


def refine_channel_groups(
    discovery,
    prepared,
    held,
    bank,
    prior,
    nodes,
    port,
    *,
    early_clock=False,
    maximum_seconds=500.0,
    training_rows=None,
    extra_starts=(),
):
    if not discovery["available"] or len(discovery["selected"]) != 3:
        raise ValueError("three sealed cold training starts required")
    if not np.isfinite(maximum_seconds) or not 0 < maximum_seconds <= 1500:
        raise ValueError("bounded refinement slice required")
    if len(extra_starts) not in (0, 3):
        raise ValueError("Extra training start control requires three matched old starts")
    selected_rows = [*discovery["selected"], *extra_starts]
    pool_rows = selected_rows if training_rows is None else training_rows
    indices = sorted(
        {i for row in pool_rows for i in row["satellite_indices"]},
        key=lambda i: bank.numbers[i],
    )
    shared_bank = bank.select(indices)
    deadline = time.monotonic() + maximum_seconds
    results = {}
    for variant in ("constant", "differential-clock"):
        results[variant] = {}
        for view, inputs in prepared.items():
            model = objective(
                inputs,
                shared_bank,
                prior,
                nodes,
                differential_clock=variant == "differential-clock",
            )
            attempts = {arm: [] for arm in ("fitted-c", "zero-c")}
            for index, row in enumerate(selected_rows):
                seed = carried_seed(
                    row,
                    pool_rows,
                    model,
                    prepared,
                    bank,
                    prior,
                    nodes,
                    early_clock,
                    nearest_timings=training_rows is not None,
                )
                for arm in attempts:
                    key = f"refine:{variant}:{view}:{index}:{arm}"
                    fit = port.get(key)
                    if fit is None:
                        if time.monotonic() + 45 >= deadline:
                            raise DiscoverySliceExpired(key)
                        try:
                            fit = fit_group_calibration(
                                model,
                                seed["vector"],
                                seed["nuisance"],
                                arm=arm,
                                seconds=45.0,
                                iterations=600,
                                local_center=seed["vector"][:2],
                                local_radius_km=25.0,
                            )
                            freeze_group_calibration(model, fit)
                        except (ValueError, TimeoutError) as error:
                            fit = dict(converged=False, reason=f"{type(error).__name__}: {error}")
                        port.put(key, fit)
                    attempts[arm].append(dict(start=index, fit=fit))
            summary = {}
            for arm, rows in attempts.items():
                eligible = [row for row in rows if row["fit"]["converged"]]
                if not eligible:
                    summary[arm] = dict(state="unavailable", reason="No stationary cold refinement")
                    continue
                winner = min(eligible, key=lambda row: (row["fit"]["objective"], row["start"]))
                fitted = winner["fit"]
                correction = freeze_group_calibration(model, fitted)
                frozen = freeze_group_position(shared_bank, fitted, correction)
                try:
                    prediction = score_frozen_group_position(
                        frozen, held[view], shared_bank, prior, HARD60_SCORE
                    )
                except ValueError as error:
                    prediction = dict(
                        state="unavailable", reason=f"{type(error).__name__}: {error}"
                    )
                summary[arm] = dict(**winner, held_prediction=prediction)
            results[variant][view] = dict(attempts=attempts, selected=summary)
    return dict(
        catalogue_numbers=shared_bank.numbers,
        results=results,
        selection="Lowest stationary training objective within each matched model/view/c arm",
        reference_usage="none",
        held_fitting="none",
        held_model_selection="none",
        starts=len(selected_rows),
    )
