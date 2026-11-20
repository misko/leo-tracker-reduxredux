"""Measure the real capped standalone command and audit its exact Graph output."""

import hashlib
import json
import resource
import runpy
import sys
from pathlib import Path
from time import perf_counter, process_time
from types import SimpleNamespace

cap = SimpleNamespace(**runpy.run_path(str(Path(__file__).with_name("cavity_reuse_observe.py"))))


def measured(unit, cpu, root, mode, flags):
    run_path = runpy.run_path

    def instrument(path, run_name):
        if run_name != "__main__":
            raise ValueError("unexpected observer entry")
        entry = run_path(path)
        entry["activate"](root)
        from leo.application.localization_v3_engine import _json_value

        from leo.application import localization_v3 as app
        from tools.pipeline_eval.variants import v5_direct_cavity as direct

        profile = {}

        def start():
            return perf_counter(), process_time()

        def end(label, clocks):
            profile[label] = dict(
                wall_s=perf_counter() - clocks[0],
                cpu_s=process_time() - clocks[1],
                rss_peak_kib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
            )

        def track_wrapper(function):
            def wrapped(*args, **kwargs):
                clocks = start()
                tracks = function(*args, **kwargs)
                end("graph_preparation", clocks)
                clocks = start()
                digest = hashlib.sha256()

                def add(value):
                    digest.update(
                        json.dumps(
                            value, default=_json_value, allow_nan=False, sort_keys=True
                        ).encode()
                    )
                    digest.update(b"\n")

                for name, value in sorted(tracks.items()):
                    add(name)
                    if name in ("tracks", "observations"):
                        for element in value:
                            add(element)
                    else:
                        add(value)
                profile["tracks_sha256"] = digest.hexdigest()
                profile["track_counts"] = dict(
                    observations=len(tracks["observations"]),
                    tracks=len(tracks["tracks"]),
                    owned=tracks["graph_points"],
                    curved=len(tracks["curved_indices"]),
                )
                end("graph_audit", clocks)
                return tracks

            return wrapped

        if mode == "winner":
            from tools.pipeline_eval.variants import winner_stream

            original = winner_stream.read

            def read(*args, **kwargs):
                clocks = start()
                value = original(*args, **kwargs)
                end("native_read", clocks)
                profile["stream_counts"] = value.counts
                return value

            winner_stream.read = read
            winner_stream.prepare = track_wrapper(winner_stream.prepare)
        else:
            original = direct.read_native

            def read(record):
                clocks = start()
                value = original(record)
                end("native_read", clocks)
                return value

            direct.read_native = read
            app.prepare_tracks = track_wrapper(app.prepare_tracks)
        entry["main"]()
        cap.emit("boundary", profile)

    runpy.run_path = instrument
    try:
        cap.measured(unit, cpu, root, flags)
    finally:
        runpy.run_path = run_path


if __name__ == "__main__":
    measured(sys.argv[1], int(sys.argv[2]), Path(sys.argv[3]), sys.argv[4], sys.argv[5:])
