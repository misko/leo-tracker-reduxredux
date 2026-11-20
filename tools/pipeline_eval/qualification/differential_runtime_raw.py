"""Use the frozen differential scorer inside the authenticated stock IQ reader."""

import json
import sys
from unittest.mock import patch

from ..variants.differential_runtime import DifferentialCall, template_edge
from . import whole_memory_chain_worker as raw


def run():
    import numpy as np

    from leo.analysis.starlink import native_short_window

    base = native_short_window.NativeShortWindow
    analyze = base.analyze
    visits = 0
    lanes_with_hint, changed_lanes = [0, 0], [0, 0]

    class DifferentialNative(base):
        def __init__(self, library, exact, control, *, sample_rate_hz, **kwargs):
            edge = template_edge(exact, control, sample_rate_hz)
            super().__init__(library, exact, control, sample_rate_hz=sample_rate_hz, **kwargs)
            self.differential = DifferentialCall(self, edge)

        def analyze(self, samples, *, include_timings=False):
            nonlocal visits
            result, proposals, trace, times = self.differential(
                samples, decode=analyze.__get__(self), timings=include_timings
            )
            hints = [centers[0] if centers else None for centers, _ in proposals]
            changed = [row["ordinary"] != row["selected"] for row in trace]
            for rx, (hint, replacement) in enumerate(zip(hints, changed, strict=True)):
                lanes_with_hint[rx] += hint is not None
                changed_lanes[rx] += replacement
            print(
                "differential-visit: "
                + json.dumps(dict(visit=visits, hints=hints, changed=changed, **times)),
                file=sys.stderr,
                flush=True,
            )
            visits += 1
            return result

    with patch.object(native_short_window, "NativeShortWindow", DifferentialNative):
        raw.raw_lane()
    print(
        "differential-runtime-result: "
        + json.dumps(
            dict(
                numpy_version=np.__version__,
                lanes_with_hint=lanes_with_hint,
                changed_lanes=changed_lanes,
                visits=visits,
            )
        ),
        file=sys.stderr,
        flush=True,
    )


if __name__ == "__main__":
    run()
