"""Physical initial correction/timing ports for shared DS21 proposals.

These are training-derived initializations, not stationary fitted states.
Persisted source coefficients are never reinterpreted in a target clock basis.
"""

from dataclasses import asdict

import numpy as np

from leo.analysis.channel_group_calibration import GroupCalibrationFrame, project_calibration_seed
from leo.analysis.frozen_group_calibration import FrozenGroupCalibration

PROPOSAL_IDS = ("cold-0", "cold-1", "cold-2", "shape-low", "shape-high", "shape-all")


def encode_initial_physical_seed(model, vector, nuisance):
    """Extract a correction function directly, without constructing a fake fit."""
    observations = model.observations
    vector, nuisance = np.asarray(vector, float), np.asarray(nuisance, float)
    dt = observations.times_s - observations.time_center_s
    affine = np.zeros((2, 2))
    for receiver in (0, 1):
        mask = observations.receiver == receiver
        if not mask.any():
            continue
        design = np.column_stack((np.ones(mask.sum()), dt[mask]))
        baseline = model.base.baseline[mask]
        affine[receiver] = np.linalg.lstsq(design, baseline, rcond=None)[0]
        if np.max(abs(design @ affine[receiver] - baseline)) > 1e-6:
            raise ValueError("non-affine baseline needs an explicit physical function")
    clock, group = model.split(nuisance)
    if model.clock_count:
        if len(clock) != 2 * model.base.null.shape[1]:
            raise ValueError("unsupported extra source clock functions")
        nodes = model.base.nodes
        knots = clock.reshape(2, -1) @ model.base.null.T
    else:
        nodes, knots = np.empty(0), np.empty((2, 0))
    state = FrozenGroupCalibration(
        observations.time_center_s,
        observations.rf_center_hz,
        model.frame,
        vector[2:7],
        affine,
        group[: model.offset_count],
        group[model.offset_count : model.offset_count + model.drift_count],
        nodes,
        knots,
        (
            group[model.offset_count + model.drift_count :].reshape(model.offset_count, -1)
            @ model.base.null.T
            if model.group_clock_count
            else None
        ),
    )
    values = state.predict(
        observations.times_s, observations.rf_hz, observations.receiver, observations.channel >= 5
    )
    expected = model.correction(vector, nuisance)
    maximum = float(np.max(abs(values - expected)))
    if maximum > 1e-6:
        raise ValueError("initial physical correction fails source closure")
    correction = asdict(state)
    for key, value in correction.items():
        if isinstance(value, np.ndarray):
            correction[key] = value.tolist()
    shifts = vector[7] + model.basis @ vector[8:]
    return {
        "physical_correction": correction,
        "physical_correction_kind": "training-derived-initialization-function",
        "source_closure_max_abs_hz": maximum,
        "orbit_timing": {
            "satellite_numbers": model.bank.numbers.tolist(),
            "shifts_s": shifts.tolist(),
        },
    }


def decode_physical_correction(entry):
    """Return the narrow predict(times,RF,receiver,high_group) physical port."""
    value = dict(entry["physical_correction"])
    frame = value.pop("frame")
    value["frame"] = GroupCalibrationFrame(
        tuple(frame["receivers"]), tuple(frame["high_fractions"])
    )
    value["group_clock_knots_hz"] = np.asarray(value["group_clock_knots_hz"], float).reshape(
        len(value["frame"].receivers), len(value["clock_nodes_s"])
    )
    return FrozenGroupCalibration(**value)


def evaluate_physical_correction(entry, observations):
    return decode_physical_correction(entry).predict(
        observations.times_s, observations.rf_hz, observations.receiver, observations.channel >= 5
    )


def project_shared_seed(entry, target_model):
    """Project into a GroupCalibrationObjective's actual bounded clock space.

    The target baseline is subtracted before projecting variable corrections;
    timing is reordered by satellite number, never by private vector position.
    Other model families can evaluate the physical port and project themselves.
    """
    values = evaluate_physical_correction(entry, target_model.observations)
    projection = project_calibration_seed(target_model, values - target_model.base.baseline)
    timing = entry["orbit_timing"]
    numbers, shifts = timing["satellite_numbers"], timing["shifts_s"]
    if len(numbers) != len(set(numbers)) or len(numbers) != len(shifts):
        raise ValueError("one physical timing per unique satellite required")
    if set(numbers) != set(target_model.bank.numbers.tolist()):
        raise ValueError("shared proposal and target candidate bank differ")
    by_number = dict(zip(numbers, shifts, strict=True))
    shifts = np.asarray([by_number[int(number)] for number in target_model.bank.numbers])
    if not np.all(np.isfinite(shifts)):
        raise ValueError("finite physical satellite timings required")
    coefficients = projection["coefficients"]
    vector = np.r_[
        entry["point_km"],
        coefficients[:5],
        shifts.mean(),
        target_model.basis.T @ (shifts - shifts.mean()),
    ]
    audit = {
        key: value.tolist() if isinstance(value, np.ndarray) else value
        for key, value in projection.items()
    }
    return {
        "vector": vector,
        "nuisance": coefficients[5:],
        "projection": audit,
        "proposal_id": entry["proposal_id"],
        "id": entry.get("id", entry["proposal_id"]),
    }


def ordered_seed_entries(cold, shape, proposals):
    """Keep all six prescribed sources, including coincident geographic points."""
    if len(cold) != 3 or len(shape) != 3 or len(proposals) != 6:
        raise ValueError("exactly three cold and three shape proposals required")
    entries = []
    for index, state in enumerate((*cold, *shape)):
        proposal = proposals[index]
        if proposal["proposal_id"] != PROPOSAL_IDS[index]:
            raise ValueError("shared proposal ordering differs")
        vector = np.asarray(state["vector"])
        if not np.array_equal(vector[:2], proposal["point_km"]):
            raise ValueError("saved seed position differs from proposal provenance")
        entries.append(dict(state, **proposal))
    return entries
