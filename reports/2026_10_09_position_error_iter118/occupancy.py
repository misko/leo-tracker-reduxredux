"""Exact uniform pilot-interval horizon occupancy; not detection probability."""

import numpy as np


def integrate(intervals, nodes, numerator, numerator_jacobian):
    """Integrate affine h(t)>=0 over disjoint fixed intervals and its derivatives.

    numerator_jacobian supplies segment-local endpoint derivatives, shape
    (nodes-1, 2, parameters), or continuous node derivatives (nodes, parameters).
    For orbit shifts use segment-local position secants: adjacent segments may
    have different timing derivatives at their shared knot. Shifted knots must
    already be expressed in receive time. Moving-knot integral boundary terms
    cancel because the horizon numerator is continuous.
    Return derivatives only away from zero-valued nodes/contact events. Splitting
    support at nodes preserves the exact piecewise-linear geometry. No NxK array.
    """
    intervals, nodes, h, jac = map(
        lambda x: np.asarray(x, dtype=float),
        (intervals, nodes, numerator, numerator_jacobian),
    )
    if jac.ndim == 2 and jac.shape[0] == len(nodes):
        jac = np.stack((jac[:-1], jac[1:]), axis=1)
    if (
        intervals.ndim != 2
        or intervals.shape[1] != 2
        or not len(intervals)
        or nodes.ndim != 1
        or len(nodes) < 2
        or h.shape != nodes.shape
        or jac.ndim != 3
        or jac.shape[:2] != (len(nodes) - 1, 2)
        or not all(np.isfinite(x).all() for x in (intervals, nodes, h, jac))
        or np.any(np.diff(nodes) <= 0)
        or np.any(intervals[:, 1] <= intervals[:, 0])
        or np.any(intervals[1:, 0] < intervals[:-1, 1])
        or intervals[0, 0] < nodes[0]
        or intervals[-1, 1] > nodes[-1]
    ):
        raise ValueError("ordered disjoint positive intervals and finite covered nodes required")
    total = float(np.sum(intervals[:, 1] - intervals[:, 0]))
    visible = 0.0
    derivative = np.zeros(jac.shape[2])
    events = []
    pieces = 0
    for start, end in intervals:
        cuts = np.concatenate(([start], nodes[(nodes > start) & (nodes < end)], [end]))
        for left, right in zip(cuts[:-1], cuts[1:], strict=True):
            pieces += 1
            i = min(int(np.searchsorted(nodes, left, side="right") - 1), len(nodes) - 2)
            span = nodes[i + 1] - nodes[i]
            a, b = (left - nodes[i]) / span, (right - nodes[i]) / span
            hl, hr = (1 - a) * h[i] + a * h[i + 1], (1 - b) * h[i] + b * h[i + 1]
            jl = (1 - a) * jac[i, 0] + a * jac[i, 1]
            jr = (1 - b) * jac[i, 0] + b * jac[i, 1]
            if hl == 0 or hr == 0:
                events.append(
                    {"left": float(left), "right": float(right), "kind": "boundary-or-flat-contact"}
                )
            if hl >= 0 and hr >= 0:
                visible += right - left
            elif hl < 0 and hr < 0:
                continue
            else:
                slope = (hr - hl) / (right - left)
                crossing = left - hl / slope
                fraction = (crossing - left) / (right - left)
                dcross = -((1 - fraction) * jl + fraction * jr) / slope
                if hl < 0:
                    visible += right - crossing
                    derivative -= dcross
                else:
                    visible += crossing - left
                    derivative += dcross
    return {
        "fraction": visible / total,
        "gradient": None if events else derivative / total,
        "events": events,
        "pieces": pieces,
        "support_seconds": total,
        "scope": "Uniform interval occupancy only; not estimator detectability",
    }
