"""Pure measurement substitution and same fitted-derived starts; no model fit."""

from copy import copy
from dataclasses import fields, replace

import numpy as np

PERIOD_HZ = 1 / 4.4e-6
VARIANTS = ("original", "logparabola", "newton")
ARMS = ("fitted-c", "zero-c")


def clone_measurement_model(model, measured_hz):
    """Clone audited B7 state; geometry/bank immutable, all model arrays independent.

    Current SlopePrior/SatelliteCorrection/DynamicRF evaluate_joint reads measured_hz
    directly and has no result cache or stored base model. Fail closed if such an
    attribute appears rather than silently retaining a measurement-dependent alias.
    """
    if any("cache" in key.lower() or key in ("base", "model", "objective") for key in vars(model)):
        raise ValueError("unreviewed model cache/base alias")
    values = np.asarray(measured_hz, float)
    if values.shape != model.observations.measured_hz.shape or not np.isfinite(values).all():
        raise ValueError("invalid replacement measurement")
    observation_fields = {
        field.name: getattr(model.observations, field.name).copy()
        for field in fields(model.observations)
        if isinstance(getattr(model.observations, field.name), np.ndarray)
    }
    observation_fields["measured_hz"] = values.copy()
    cloned = copy(model)
    cloned.observations = replace(model.observations, **observation_fields)
    for key, value in vars(model).items():
        if isinstance(value, np.ndarray):
            setattr(cloned, key, value.copy())
    return cloned


def substitute(window_ids, measured_hz, rows, variant):
    """Keep original branch/order. Require every original row to pass frozen128."""
    if variant not in VARIANTS:
        raise ValueError("unknown variant")
    ids = list(window_ids)
    values = np.asarray(measured_hz, float)
    if values.shape != (len(ids),) or not np.isfinite(values).all():
        raise ValueError("invalid original measurements")
    row_ids = [row["window_id"] for row in rows]
    if len(ids) != len(set(ids)) or len(row_ids) != len(set(row_ids)) or set(ids) != set(row_ids):
        raise ValueError("full original membership required")
    lookup = {row["window_id"]: row for row in rows}
    delta = np.zeros(len(ids))
    wraps = np.zeros(len(ids), dtype=int)
    for index, window_id in enumerate(ids):
        row = lookup[window_id]
        if row["status"] != "complete" or row["result"]["parity"] != "passed":
            raise ValueError("every original observation must pass128 parity")
        result = row["result"]
        if (
            result["scorer_kind"] != "original-python-conditioned-scorer"
            or not result["original_passed"]
        ):
            raise ValueError("original scorer/admission differs")
        baseline = result["baseline_cfo_hz"]
        if not np.isfinite(baseline) or abs(values[index] - baseline) > 1e-6:
            raise ValueError("baseline frequency identity differs")
        # Validate both frozen refiners for all comparisons, including control.
        for name in VARIANTS[1:]:
            candidate = result[f"{name}_cfo_hz"]
            if not np.isfinite(candidate):
                raise ValueError("nonfinite refined frequency")
            raw = candidate - baseline
            circular = (raw + PERIOD_HZ / 2) % PERIOD_HZ - PERIOD_HZ / 2
            change = result["changes"][name]
            wrap = int(round((raw - circular) / PERIOD_HZ))
            if abs(circular - change["circular_hz"]) > 1e-6 or wrap != change["wrap_count"]:
                raise ValueError("circular-change receipt differs")
            if name == variant:
                delta[index], wraps[index] = circular, wrap
    return {
        "measured_hz": values.copy() + delta,
        "circular_delta_hz": delta,
        "representation_wraps": wraps,
        "window_ids": ids,
    }


def shared_starts(vector, clock, *, rf_clock_columns, fixed_rf_drift=False):
    """Explicit RF columns avoid assumptions about appended nuisance blocks."""
    physical = np.asarray(vector, float)
    nuisance = np.asarray(clock, float)
    indices = np.asarray(rf_clock_columns, int)
    if physical.ndim != 1 or len(physical) < 8 or nuisance.ndim != 1:
        raise ValueError("invalid start shape")
    if (
        indices.shape != (2,)
        or len(set(indices)) != 2
        or np.any(indices < 0)
        or np.any(indices >= len(nuisance))
    ):
        raise ValueError("exact two RF-time column indices required")
    if not np.isfinite(physical).all() or not np.isfinite(nuisance).all():
        raise ValueError("nonfinite shared fitted start")
    starts = {}
    for variant in VARIANTS:
        for arm in ARMS:
            v, c = physical.copy(), nuisance.copy()
            if arm == "zero-c":
                v[6] = 0
            if arm == "zero-c" or fixed_rf_drift:
                c[indices] = 0
            starts[(variant, arm)] = {"vector": v, "clock_coefficients": c}
    return starts
