"""Reuse the selected arm's complete zero-start, zero-reference first fit."""

from copy import deepcopy

import numpy as np

from leo.contracts import localization_v5

POLICY = localization_v5.INITIAL_CONTROL_POLICY


def initial_control(winner, arm):
    first = winner["arms"][arm]["phase_rounds"][0]
    reference = np.asarray(first["phase_reference"])
    start = np.asarray(first["fit"]["history"][0]["parameters"])
    if (type(first["epoch"]) is not int or first["epoch"] != 0
            or reference.ndim != 1 or not reference.size or np.any(reference != 0)
            or start.shape != (2,) or np.any(start != 0)):
        raise ValueError("Initial control requires epoch zero, zero reference and zero start")
    return deepcopy(first["fit"])
