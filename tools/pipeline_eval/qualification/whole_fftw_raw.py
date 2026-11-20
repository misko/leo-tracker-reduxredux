"""Supply the qualified FFTW scorer inside the ordinary authenticated raw lane."""

import sys
from pathlib import Path
from unittest.mock import patch

from .. import whole_iq
from ..variants.differential_runtime import DifferentialCall
from ..variants.differential_runtime_fft import FftScout
from . import differential_runtime_raw

SCOUT_NAME = "libdifferential-scout.so"
SCOUT_SHA256 = "558e5832a1e489c23bff6ec2dd3203a780b9473c7e8284c00290621ee269c4f8"


def library(detector):
    return whole_iq.checked(detector.with_name(SCOUT_NAME), SCOUT_SHA256)


def run():
    from leo.analysis.starlink import native_short_window

    scout_library = library(Path(sys.argv[sys.argv.index("--native-library") + 1]))

    class FftWindow(native_short_window.NativeShortWindow):
        def close(self):
            scout = getattr(self, "fftw_scout", None)
            try:
                if scout is not None:
                    scout.__exit__(None, None, None)
            finally:
                super().close()

    def create_call(native, edge):
        native.fftw_scout = FftScout(scout_library, edge)
        return DifferentialCall(native, edge, scout=native.fftw_scout)

    with (
        patch.object(native_short_window, "NativeShortWindow", FftWindow),
        patch.object(differential_runtime_raw, "DifferentialCall", create_call),
    ):
        differential_runtime_raw.run()


if __name__ == "__main__":
    run()
