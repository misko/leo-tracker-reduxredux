"""Run the stock-first incremental ABI from the authenticated whole-IQ reader."""

import json
import sys
from hashlib import file_digest
from pathlib import Path
from unittest.mock import patch

from . import differential_runtime_raw


def run():
    from leo.analysis.starlink import native_short_window

    from ..variants.incremental_rescue import IncrementalRescueCall, SingleLaneScout

    detector = Path(sys.argv[sys.argv.index("--native-library") + 1])
    binding = json.loads((detector.parent / "raw-release.json").read_bytes())
    for spec in binding.values():
        with Path(spec["path"]).open("rb") as stream:
            if file_digest(stream, "sha256").hexdigest() != spec["sha256"]:
                raise ValueError(
                    "the whole incremental kernel or sidecar changed before raw replay"
                )
    if Path(binding["detector"]["path"]).resolve() != detector.resolve():
        raise ValueError("the raw worker opened a different incremental detector")
    scout_library = Path(binding["scout"]["path"])

    class IncrementalWindow(native_short_window.NativeShortWindow):
        def close(self):
            scout = getattr(self, "incremental_scout", None)
            try:
                if scout is not None:
                    scout.__exit__(None, None, None)
            finally:
                super().close()

    def factory(native, edge):
        native.incremental_scout = SingleLaneScout(scout_library, edge)
        invoke = IncrementalRescueCall(native, edge, scout=native.incremental_scout)

        def measure(samples, *, decode=None, timings=False):
            result, proposals, trace, times = invoke(samples, decode=decode, timings=timings)
            times = dict(times, incremental_lanes=trace)
            for clock in ("cpu", "wall"):
                times["native_" + clock + "_ns"] = (
                    times["stock_" + clock + "_ns"] + times["rescue_" + clock + "_ns"]
                )
            centers = [
                dict(ordinary=row["ordinary"], selected=row["ordinary"] + row["selected"])
                for row in trace
            ]
            return result, proposals, centers, times

        return measure

    with (
        patch.object(native_short_window, "NativeShortWindow", IncrementalWindow),
        patch.object(differential_runtime_raw, "DifferentialCall", factory),
    ):
        differential_runtime_raw.run()


if __name__ == "__main__":
    run()
