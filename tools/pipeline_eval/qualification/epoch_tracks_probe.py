"""Observe the selected track builder at the normal phase-release entry point."""

import json
import runpy
from time import perf_counter, process_time


def setup(target, method, trace_path):
    from leo.application import localization_v3

    if method == "epoch":
        from tools.pipeline_eval.variants.epoch_tracks import prepare_tracks
    elif method == "graph":
        prepare_tracks = localization_v3.prepare_tracks
    else:
        raise ValueError("unexpected track builder in worker handoff")
    trace = runpy.run_path(str(trace_path))["trace"]

    def measured(document, config):
        cpu, wall = process_time(), perf_counter()
        result = prepare_tracks(document, config)
        (target / "track-stage.json").write_text(
            json.dumps(
                dict(
                    method=method,
                    cpu_s=process_time() - cpu,
                    wall_s=perf_counter() - wall,
                    observations=len(result["observations"]),
                    tracks=len(result["tracks"]),
                    curved=len(result["curved_indices"]),
                    points=result["graph_points"],
                    status=result["status"],
                    **result.get("epoch_track_receipt", {}),
                )
            )
        )
        trace(result, target / "tracks.json")
        return result

    localization_v3.prepare_tracks = measured
