"""Run the exact fifth-center ABI inside the authenticated stock dual-IQ lane."""

import sys
from pathlib import Path
from unittest.mock import patch

from ..variants.differential_runtime_fft import FftScout
from . import differential_runtime_raw, whole_fftw_raw


def run():
    from leo.analysis.starlink import native_short_window

    from ..variants.center_union import DifferentialUnionCall

    detector = Path(sys.argv[sys.argv.index("--native-library") + 1])
    fftw = whole_fftw_raw.library(detector)

    class FftWindow(native_short_window.NativeShortWindow):
        def close(self):
            scout = getattr(self, "fftw_scout", None)
            try:
                if scout is not None:
                    scout.__exit__(None, None, None)
            finally:
                super().close()

    def create(native, edge):
        native.fftw_scout = FftScout(fftw, edge)
        union = DifferentialUnionCall(native, edge, scout=native.fftw_scout)

        def measure(samples, *, decode=None, timings=False):
            result, proposals, lane_trace, times = union(samples, decode=decode, timings=timings)
            times["center_union_lanes"] = lane_trace
            return result, proposals, lane_trace, times

        return measure

    with (
        patch.object(native_short_window, "NativeShortWindow", FftWindow),
        patch.object(differential_runtime_raw, "DifferentialCall", create),
    ):
        differential_runtime_raw.run()


if __name__ == "__main__":
    run()
