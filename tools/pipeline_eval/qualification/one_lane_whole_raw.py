"""Run the stock raw reader with one actual physical native context per worker."""

import sys
from pathlib import Path
from unittest.mock import patch

from .. import whole_iq
from ..variants.single_chain import analyze_native
from .whole_memory_chain_worker import raw_lane


def stereo_slots(result, lane):
    (observed,) = result["rows"]
    if observed["receiver_id"] != lane:
        raise ValueError("candidate row does not belong to the selected physical lane")
    empty = dict(observed, receiver_id=1 - lane, candidates=[])
    return dict(result, rows=[observed, empty] if lane == 0 else [empty, observed])


def run():
    from leo.analysis.starlink import native_short_window
    from leo.storage import fast_scan

    library = Path(sys.argv[sys.argv.index("--native-library") + 1])
    ident = sys.argv[sys.argv.index("--case") + 1]
    source = whole_iq.read(library.parents[2] / "source-lock.json")
    authority = source["cases"][ident]["dispatch"]
    rows = whole_iq.read(whole_iq.checked(Path(authority["path"]), authority["sha256"]))
    planned = {row["visit"]: row for row in rows}
    selected = None
    executed = False
    base = native_short_window.NativeShortWindow
    source_windows = fast_scan.FastSegmentSource.windows

    class SingleNative:
        def __init__(self, *args, receiver_count, **kwargs):
            if receiver_count != 2:
                raise ValueError("the capture adapter requires the original stereo geometry")
            self.native = base(*args, receiver_count=1, **kwargs)

        def analyze(self, samples, *, include_timings=False):
            nonlocal executed
            if selected is None or executed:
                raise ValueError("the detector must run once per declared valid physical visit")
            executed = True
            result = analyze_native(
                self.native, samples, receiver_id=selected, include_timings=include_timings
            )
            return stereo_slots(result, selected)

        def __enter__(self):
            self.native.__enter__()
            return self

        def __exit__(self, *args):
            return self.native.__exit__(*args)

    def route(source):
        nonlocal selected, executed
        if source.receiver_ids != (0, 1):
            raise ValueError("raw visit differs from the frozen physical stereo geometry")
        for window in source_windows(source):
            row = planned.get(int(window.acquisition["global_visit"]))
            if row is not None and window.target["rf_center_hz"] != row["rf_center_hz"]:
                raise ValueError("raw visit differs from the authentically recorded RF schedule")
            selected = row["selected_receiver"] if row is not None else None
            executed = False
            yield window
            if executed != (row is not None):
                raise ValueError("actual validity differs from the independently sealed dispatch")
            selected = None

    with (
        patch.object(native_short_window, "NativeShortWindow", SingleNative),
        patch.object(fast_scan.FastSegmentSource, "windows", route),
    ):
        raw_lane()


if __name__ == "__main__":
    run()
