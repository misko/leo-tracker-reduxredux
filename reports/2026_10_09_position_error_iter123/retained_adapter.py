"""Pure admission and symmetric retained-region continuation policy."""

import copy
import math


def admitted_original(point, seed, fitted, bank_count):
    indices = seed["satellite_indices"]
    if len(indices) < 2 or len(set(indices)) != len(indices):
        raise ValueError("invalid satellite subset")
    if any(type(i) is not int or not 0 <= i < bank_count for i in indices):
        raise ValueError("satellite index outside bound bank")
    for vector in (seed["vector"], fitted["vector"]):
        if len(vector) != 7 + len(indices) or not all(math.isfinite(x) for x in vector):
            raise ValueError("invalid coarse vector")
        if list(vector[:2]) != list(point):
            raise ValueError("coarse position differs from retained point")
    if not math.isfinite(fitted["objective"]):
        raise ValueError("nonfinite native objective")
    return copy.deepcopy(dict(bootstrap=seed, fits={"V16": {"fit": fitted}}))


def continue_branch(case, triggers, stage, *, recover, joint):
    """Three independent regions; no union or cross-policy winner selection."""
    if len(triggers) != 3 or len({t["key"] for t in triggers}) != 3:
        raise ValueError("exactly three distinct sealed regions required")
    regions = {}
    for index, trigger in enumerate(triggers):
        regions[f"retained-{index}"] = recover(
            case["observations"], case["bank"], case["prior"], trigger, stage
        )
    operational, attempts, reasons = joint(
        case["observations"], case["bank"], case["prior"], regions, stage
    )
    return dict(regions=regions, operational=operational, attempts=attempts, reasons=reasons)
