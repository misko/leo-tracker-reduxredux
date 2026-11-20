"""Load the locked multilag FFTW scout inside the standard complete CI16 replay."""

import json
import sys
from hashlib import file_digest
from pathlib import Path
from unittest.mock import patch

from . import differential_runtime_raw


def run():
    from leo.analysis.starlink import native_short_window

    from ..variants.center_union import DifferentialUnionCall
    from ..variants.multilag_search import MultilagScout

    detector = Path(sys.argv[sys.argv.index("--native-library") + 1])
    assets = json.loads((detector.parent / "raw-release.json").read_bytes())
    if detector.resolve() != Path(assets["candidate"]["path"]).resolve():
        raise ValueError("raw worker opened another fifth-center detector")
    for binding in assets.values():
        with Path(binding["path"]).open("rb") as stream:
            if file_digest(stream, "sha256").hexdigest() != binding["sha256"]:
                raise ValueError("multilag raw detector or scout differs from its source lock")

    class MultilagWindow(native_short_window.NativeShortWindow):
        def close(self):
            scout = getattr(self, "multilag_scout", None)
            try:
                if scout is not None:
                    scout.__exit__(None, None, None)
            finally:
                super().close()

    def construct(native, edge):
        native.multilag_scout = MultilagScout(assets["scout"]["path"], edge)
        call = DifferentialUnionCall(native, edge, scout=native.multilag_scout)

        def measure(samples, *, decode=None, timings=False):
            result, proposals, traces, times = call(samples, decode=decode, timings=timings)
            times["center_union_lanes"] = traces
            return result, proposals, traces, times

        return measure

    with (
        patch.object(native_short_window, "NativeShortWindow", MultilagWindow),
        patch.object(differential_runtime_raw, "DifferentialCall", construct),
    ):
        differential_runtime_raw.run()


if __name__ == "__main__":
    run()
