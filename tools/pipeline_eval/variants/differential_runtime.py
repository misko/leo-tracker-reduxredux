"""Opt-in differential scout followed by the four-center hinted wide detector."""

from time import perf_counter_ns, process_time_ns
from unittest.mock import patch

import numpy as np

from . import differential_pilot, hinted_glrt


def template_edge(exact, control, rate):
    """Identify the recording edge from the two templates actually supplied to GLRT."""
    from leo.analysis.starlink.templates import CONTROL_SYMBOL_ROLL, qin_edge_pilot_frame

    if rate != differential_pilot.RATE:
        raise ValueError("the differential scout requires 10 MS/s")
    for edge in ("lower", "upper"):
        if np.array_equal(exact, qin_edge_pilot_frame(rate, edge)) and np.array_equal(
            control, qin_edge_pilot_frame(rate, edge, symbol_roll=CONTROL_SYMBOL_ROLL)
        ):
            return edge
    raise ValueError("the scout requires the detector's standard exact and control Qin templates")


class DifferentialCall:
    """Compute rank-one proposals independently for each physical receiver."""

    def __init__(self, native, edge, *, scout=differential_pilot.scout):
        self.native = native
        self.edge = edge
        self.scout = scout
        self.hinted = hinted_glrt.HintedCall(native)

    def __call__(self, samples, *, decode=None, timings=False):
        start_cpu, start_wall = process_time_ns(), perf_counter_ns()
        proposals = self.scout(samples, self.edge)
        hints = tuple(centers[0] if centers else None for centers, _ in proposals)
        scout_cpu, scout_wall = process_time_ns(), perf_counter_ns()
        if decode is None:
            result, trace = self.hinted(samples, hints, timings=timings)
        else:
            # The captured decoder is the stock method even when a raw replay wrapper
            # temporarily instruments the class's public analyze method.
            with patch.object(self.native, "analyze", decode):
                result, trace = self.hinted(samples, hints, timings=timings)
        elapsed = dict(
            scout_cpu_ns=scout_cpu - start_cpu,
            scout_wall_ns=scout_wall - start_wall,
            native_cpu_ns=process_time_ns() - scout_cpu,
            native_wall_ns=perf_counter_ns() - scout_wall,
        )
        return result, proposals, trace, elapsed
