"""Assemble the released curved likelihood design directly in output row order."""

from collections import Counter
from contextlib import ExitStack, contextmanager
from hashlib import sha256
from inspect import getsource
from pathlib import Path
from textwrap import dedent, indent
from time import process_time_ns
from unittest.mock import patch

import numpy as np

from leo.analysis.localization_v3 import history_position, marginal, position

SOURCE_PINS = {
    marginal: "c80ac51249578e8a2c6c6a13a04aaa22a168353b2c758155858106b91507b609",
    history_position: "00e349de1a25ac62fb287f970a005737675b5f2e6d45273baa9c914e8a7918f0",
    position: "c3507e6ecaba0adf6d3677f56d8056afcccbcf90d6a561bca7a42b06b0daef9d",
}


def direct_features(problem, derivative, modes, scales):
    """Fill a fresh C-order matrix using the stock elementwise operations."""
    rows = len(derivative)
    hardware_end = problem.hardware.shape[1]
    smooth_end = hardware_end + problem.smooth.shape[1]
    orbit_start = smooth_end + len(problem.labels)
    orbit_end = orbit_start + 3 * len(problem.supported)
    features = np.empty((rows, orbit_end + problem.constants.shape[1]))

    features[:, :hardware_end] = problem.hardware
    features[:, [4, 6]] *= 10 * scales[0]
    smooth = features[:, hardware_end:smooth_end]
    np.multiply(problem.smooth, 200, out=smooth)
    np.multiply(smooth, scales[1], out=smooth)
    features[:, smooth_end:orbit_end] = 0.0
    features[:, orbit_end:] = problem.constants

    labels = problem.flat_labels
    features[np.arange(rows), smooth_end + labels] = (
        problem.q * derivative * problem.phase_sigma[labels]
    )
    if problem.supported_local:
        # Each row belongs to one family. Scatter its three orbital entries
        # once, with the same individual multiplications as the released loop.
        family_slot = np.full(len(problem.labels), -1, dtype=np.intp)
        family_slot[list(problem.supported_local)] = np.arange(len(problem.supported_local))
        slots = family_slot[labels]
        active = np.flatnonzero(slots >= 0)
        columns = orbit_start + 3 * slots[active, None] + np.arange(3)
        features[active[:, None], columns] = problem.q[active, None] * modes[active] * scales[2]
    return features


def selected_design(features, scale, keep):
    """Keep original row order and multiply only rows reaching the bound."""
    out = features[keep]
    np.multiply(out, scale, out=out)
    return out


def _replace(source, before, after):
    if source.count(before) != 1:
        raise ValueError(f"Expected exactly one released preparation block: {before!r}")
    return source.replace(before, after)


def _compile(source, module, name, **extras):
    names = dict(vars(module), **extras)
    exec(compile(source, module.__file__, "exec"), names)
    return names[name]


@contextmanager
def measured_curved_design(*, enabled):
    """Measure assembly independently of projection, posterior and readout."""
    from leo.analysis.localization_v3 import (
        event_position,
        history_policy,
        prediction,
        predictive_linear,
    )

    for module, expected in SOURCE_PINS.items():
        if sha256(Path(module.__file__).read_bytes()).hexdigest() != expected:
            raise ValueError(f"Unreviewed curved design source: {module.__name__}")

    counts = Counter()
    joint = dedent(getsource(marginal.JointMarginal.calculate))
    first = joint.index("    phases = ")
    last = joint.index("    raw = ", first)
    stock_assembly = _compile(
        "def stock(self, frequency, derivative, modes, scales):\n"
        + joint[first:last] + "    return features\n",
        marginal, "stock",
    )

    def assemble(problem, frequency, derivative, modes, scales, geometry_only):
        start = process_time_ns()
        # These released non-empirical models always use 64-bit arrays and
        # one distinct local slot per supported family. Read current values
        # on every call, including topology, scales, masks, and feature columns.
        eligible = (
            geometry_only and type(problem.flat_labels) is np.ndarray
            and problem.variant == "radio_noise"
            and len(problem.supported) == len(problem.supported_local)
            and len(set(problem.supported_local)) == len(problem.supported_local)
            and all(a.dtype == np.float64 for a in (
                problem.hardware, problem.smooth, problem.constants, problem.q,
                derivative, modes, problem.phase_sigma, scales,
            ))
        )
        use_direct = enabled and eligible
        result = (direct_features(problem, derivative, modes, scales) if use_direct
                  else stock_assembly(problem, frequency, derivative, modes, scales))
        key = "direct_assembly" if use_direct else "released_assembly"
        counts[key + "_ns"] += process_time_ns() - start
        counts[key + "_calls"] += 1
        return result

    def selector(method):
        def select(features, scale, keep):
            start = process_time_ns()
            # Released base output is always a fresh float64 matrix and the
            # selected scales are finite positive float64 (1.0 or 0.3).
            use_direct = (enabled and type(features) is np.ndarray
                          and features.dtype == scale.dtype == np.float64
                          and keep.dtype == np.bool_ and keep.ndim == 1)
            result = (selected_design(features, scale, keep) if use_direct
                      else (features * scale)[keep])
            counts[method + "_selection_ns"] += process_time_ns() - start
            counts[method + "_selection_calls"] += 1
            counts[method + "_selection_direct"] += use_direct
            return result

        return select

    joint = joint[:first] + indent(
        "features = _assemble(self, frequency, derivative, modes, scales, geometry_only)\n", "    "
    ) + joint[last:]
    joint_calculate = _compile(joint, marginal, "calculate", _assemble=assemble)
    normal = dedent(getsource(position.NormalPosition.calculate))
    normal = _replace(normal, "design, response, noise = features * scales, raw, self.point_noise",
                      "design, response, noise = features, raw, self.point_noise")
    normal = _replace(normal, "design[self.keep]", "_select(design, scales, self.keep)")
    normal_calculate = _compile(normal, position, "calculate", _select=selector("normal"))
    make_problem = history_position.make_problem
    history = _replace(getsource(make_problem), "(features * scale)[keep]",
                       "_select(features, scale, keep)")
    history_problem = _compile(
        history, history_position, "make_problem", _select=selector("history"),
    )
    callers = (history_position, event_position, history_policy, prediction, predictive_linear)
    with ExitStack() as stack:
        stack.enter_context(patch.object(marginal.JointMarginal, "calculate", joint_calculate))
        stack.enter_context(patch.object(position.NormalPosition, "calculate", normal_calculate))
        for module in callers:
            if getattr(module, "make_problem", None) is make_problem:
                stack.enter_context(patch.object(module, "make_problem", history_problem))
        yield counts
