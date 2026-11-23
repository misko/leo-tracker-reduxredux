"""Evaluate the actual full-short graph settings on the installed DS30-0008 detector packet."""

from contextlib import ExitStack, contextmanager
from dataclasses import asdict
from functools import wraps
from hashlib import sha256
from inspect import getsource
import json
from pathlib import Path
from time import perf_counter, process_time
from unittest.mock import patch

from live_inference_profile import replay


HERE = Path(__file__).resolve().parent
LIVE_ROUTE_PIN = "b3d103b1a105fd507f8471197479098348eda180e38131c638dda878e9c055d1"
CONTROL_PIN = "22f6a006e0958476c4a46591af1c1159e8f4c95ed60a13604db57831e20bbd79"


def timed(operation, ledgers, key):
    rows = ledgers.setdefault(key, [])

    @wraps(operation)
    def observe(*args, **kwargs):
        cpu, wall = process_time(), perf_counter()
        try:
            return operation(*args, **kwargs)
        finally:
            rows.append(dict(cpu_s=process_time()-cpu, elapsed_s=perf_counter()-wall))

    return observe


class GraphAudit:
    def __init__(self):
        self.result = None
        self.clocks = {}

    @contextmanager
    def configure(self, assets, route):
        from leo.analysis.localization_v3 import tracks
        from leo.application import localization_v3
        from tools import algo08_position
        from full_short_raw import graph_config

        route_pin = sha256(getsource(route).encode()).hexdigest()
        if route_pin != LIVE_ROUTE_PIN:
            raise ValueError("The live route differs from the sealed control constructor")
        factory = algo08_position.TrackConfig
        preparation = localization_v3.prepare_tracks
        cfg_path = assets / "tracks.json"
        cfg = cfg_path.read_bytes()
        installed = factory(**json.loads(cfg)["config"])
        self.identity = dict(live_route_sha256=route_pin, track_asset_sha256=sha256(cfg).hexdigest(),
                             control=asdict(installed), quadratic=asdict(graph_config(installed)),
                             input="installed v3 saved detector proxy")

        def prepare(document, config):
            if self.result is not None or config != graph_config(installed):
                raise ValueError("Expected a single full-short quadratic graph preparation")
            self.result = preparation(document, config)
            return self.result

        with ExitStack() as scope:
            scope.enter_context(patch.object(algo08_position, "TrackConfig", lambda **values: graph_config(factory(**values))))
            scope.enter_context(patch.object(localization_v3, "prepare_tracks", timed(prepare, self.clocks, "prepare_tracks")))
            for name in ("winning_observations", "graph_tracks", "_single_rf_tracks"):
                scope.enter_context(patch.object(tracks, name, timed(getattr(tracks, name), self.clocks, name)))
            yield

    def report(self):
        from leo.application.localization_v3_engine import _json_value
        from leo.contracts.digests import canonical_digest

        graph = self.result
        if graph is None or any(len(self.clocks[name]) != 1 for name in ("prepare_tracks", "graph_tracks", "winning_observations")):
            raise ValueError("The quadratic graph did not run through the installed preparation entry")
        fits = graph["tracks"]
        return dict(graph=dict(**self.identity, clocks=self.clocks, status=graph["status"],
                               graph_sha256=canonical_digest(json.loads(json.dumps(graph, default=_json_value))),
                               observation_sha256=canonical_digest(graph["observations"]), observations=len(graph["observations"]),
                               tracks=len(fits), active_curvature=len(graph["curved_indices"]), graph_points=graph["graph_points"],
                               path_extracted=sum(t.get("diagnostics", {}).get("graph_paths_extracted", 0) for t in fits),
                               piece_degrees={degree: sum(p["degree"] == degree for t in fits for p in t["pieces"])
                                              for degree in range(5)}),
                    experiment_source_sha256=sha256(Path(__file__).read_bytes()).hexdigest())


def run(output):
    graph = GraphAudit()
    replay("control", output, configure_solve=graph.configure, result_details=graph.report)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    run(parser.parse_args().output)
