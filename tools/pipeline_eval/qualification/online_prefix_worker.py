"""Record support from the normal smooth-clock fit without changing its estimates."""

import json
import sys
from resource import RLIMIT_AS, setrlimit
from unittest.mock import patch

from tools.pipeline_eval.variants import native_lean as native


def support(rows, satellites):
    selected = {}
    for row in rows:
        tr = row.arc.track
        norad = str(satellites[row.orbit].satnum)
        item = selected.setdefault(
            norad, dict(earliest_s=float(tr.t[0]), latest_s=0.0, points=0, lanes=[])
        )
        item["earliest_s"] = min(item["earliest_s"], float(tr.t[0]))
        item["latest_s"] = max(item["latest_s"], float(tr.t[-1]))
        item["points"] += len(tr.t)
        item["lanes"] = sorted(set(item["lanes"]) | {int(tr.lane)})
    return selected


def worker(request):
    limit = native.AS_LIMIT_MIB * 1024**2
    setrlimit(RLIMIT_AS, (limit, limit))
    from tools.pipeline_eval.qualification import native_clock_model_worker as clock
    from tools.pipeline_eval.variants import joint_clock_model, robust_orbit_fit

    grid = robust_orbit_fit.grid
    satellites, owners = [], {}
    measured = {}
    original_valid, original_refine = grid._valid_states, joint_clock_model.refine
    original_graph = native.graph_projection

    def valid(*args):
        outcome = original_valid(*args)
        satellites[:] = outcome[0]
        return outcome

    def refine(rows, start, tile, region, half, arm, *, clock):
        output = original_refine(rows, start, tile, region, half, arm, clock=clock)
        owners[arm] = support(rows, satellites)
        return output

    def graph(lanes, config):
        tracks = original_graph(lanes, config)
        measured["latest_graph_time_s"] = max((row["times"][-1] for row in tracks), default=0.0)
        measured["graph_tracks"] = len(tracks)
        return tracks

    with (
        patch.object(grid, "_valid_states", valid),
        patch.object(joint_clock_model, "refine", refine),
        patch.object(native, "graph_projection", graph),
    ):
        result = clock.worker(request)
    result["orbit_support"] = owners
    return dict(result, **measured)


if __name__ == "__main__":
    begin = native._now()
    outcome = worker(json.load(sys.stdin))
    outcome["worker"] = native._elapsed(begin)
    json.dump(outcome, sys.stdout, sort_keys=True, allow_nan=False)
