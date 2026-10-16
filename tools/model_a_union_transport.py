"""Pure bank-union and physical timing transport ports; no optimizer or truth."""

from copy import deepcopy

import numpy as np

from leo.contracts.regional_position import PositionOrbitBank


def union_bank(before, after):
    if not np.array_equal(before.nodes_s, after.nodes_s):
        raise ValueError("Union orbit interpolation nodes differ")
    lookup = {}
    for bank in (before, after):
        for i, number in enumerate(bank.numbers):
            number = int(number)
            state = (bank.position_km[i], bank.velocity_km_s[i])
            if number in lookup and any(
                not np.array_equal(a, b) for a, b in zip(lookup[number], state, strict=True)
            ):
                raise ValueError("Common satellite orbit arrays differ")
            lookup[number] = state
    numbers = sorted(lookup)
    return PositionOrbitBank(
        np.asarray(numbers),
        before.nodes_s.copy(),
        np.stack([lookup[n][0] for n in numbers]),
        np.stack([lookup[n][1] for n in numbers]),
    )


def transport(seed, original, target):
    """Retain existing absolute timing; added satellites use original common shift."""
    vector, nuisance = np.asarray(seed["vector"], float), np.asarray(seed["nuisance"], float)
    if vector.shape != (original.size,) or nuisance.shape != original.initial_nuisance.shape:
        raise ValueError("Original seed layout differs")
    if (
        original.frame != target.frame
        or original.score != target.score
        or original.prior != target.prior
        or original.clock_count != target.clock_count
        or original.observations.window_ids != target.observations.window_ids
        or nuisance.shape != target.initial_nuisance.shape
        or not np.isfinite(vector).all()
        or not np.isfinite(nuisance).all()
    ):
        raise ValueError("Physical calibration frame, score or observations differ")
    for name in ("design", "group_design", "group_precision"):
        if not np.array_equal(getattr(original, name), getattr(target, name)):
            raise ValueError("Physical calibration design differs")
    if not np.array_equal(original.base.baseline, target.base.baseline) or (
        original.clock_count
        and not np.array_equal(original.base.clock_design, target.base.clock_design)
    ):
        raise ValueError("Physical clock or baseline differs")
    old, new = original.bank.numbers.tolist(), target.bank.numbers.tolist()
    if not set(old) <= set(new) or len(set(old)) != len(old) or len(set(new)) != len(new):
        raise ValueError("Union must contain every unique original satellite")
    relative = original.basis @ vector[8:]
    absolute = vector[7] + relative
    lookup = dict(zip(old, absolute, strict=True))
    desired = np.asarray([lookup.get(n, vector[7]) for n in new])
    common = float(desired.mean())
    carried = np.r_[vector[:7], common, target.basis.T @ (desired - common)]
    reconstructed = carried[7] + target.basis @ carried[8:]
    if not np.allclose(reconstructed, desired, rtol=0, atol=1e-12):
        raise ValueError("Absolute timing transport failed")
    if abs(common) > 10 + 1e-10:
        raise ValueError("Transported common timing violates original bound")
    correction_error = float(
        np.max(
            abs(original.correction(vector, nuisance) - target.correction(carried, nuisance)),
            initial=0,
        )
    )
    if correction_error > 1e-7:
        raise ValueError("Transport changed physical calibration correction")
    result = deepcopy(seed)
    result["vector"], result["nuisance"] = carried, nuisance.copy()
    result["timing_transport"] = dict(
        original_numbers=old,
        target_numbers=new,
        original_shifts_s=absolute.tolist(),
        target_shifts_s=reconstructed.tolist(),
        added_shift_rule="Source common timing, zero relative shift",
        maximum_timing_closure_s=float(np.max(abs(reconstructed - desired))),
        maximum_correction_closure_hz=correction_error,
    )
    return result


def validate_domain(seed, target, center, *, radius=25):
    """Audit the untouched seed against the original fit domain; never clip it."""
    from leo.analysis.hard60_bounded_fit import _Problem

    vector, nuisance = np.asarray(seed["vector"]), np.asarray(seed["nuisance"])
    problem = _Problem(target, vector, local_center=center, local_radius_km=radius)
    limits = np.r_[np.full(target.clock_count, 2000.0), target.group_limits]
    if not problem.feasible(vector) or np.any(abs(nuisance) > limits + 1e-7):
        raise ValueError("Carried seed violates original physical/nuisance bounds")
    return dict(
        physical_constraint_minimum=float(np.min(problem.constraints(vector))),
        original_fitter_internal_start_adjustment_maximum=float(
            np.max(abs(problem.start - vector), initial=0)
        ),
        nuisance_bound_minimum=None if not len(limits) else float(np.min(limits - abs(nuisance))),
        domain="Original fitted-c slope60,c5000,common10,physical timing20,clock2000; own25km disk",
    )
