"""Measure the quadratic graph gate on the same authenticated saved input."""

import argparse
from contextlib import ExitStack, contextmanager
import cProfile
from hashlib import sha256
from pathlib import Path
from time import process_time
from unittest.mock import patch

from aperture_trial import write
from dense_quadratic_proxy import GraphAudit
from live_inference_profile import attribution, replay


class GraphDone(Exception):
    pass


def trial(output, mode):
    if mode == "endpoint-full":
        from aperture_trial import read
        from dense_quadratic_proxy_score import graph_gate

        prior = read(output.parent / "quadratic.json")
        gate, _ = graph_gate(output.parent, prior["graph"]["graph_sha256"])
        if not gate["full_replay_allowed"]:
            raise ValueError("The matched graph-only timing gate did not pass")
    audit = GraphAudit()
    profiler = cProfile.Profile(timer=process_time) if mode == "profile" else None
    counters = {}
    endpoint = mode in ("endpoint", "endpoint-full")

    def receipt():
        return dict(**audit.report(), kernel=counters, graph_trial_mode=mode,
                    graph_trial_sha256=sha256(Path(__file__).read_bytes()).hexdigest())

    @contextmanager
    def configure(assets, route):
        from leo.application import localization_v3

        with ExitStack() as scope:
            scope.enter_context(audit.configure(assets, route))
            if endpoint:
                from quadratic_endpoint_slope import endpoint_slope

                counts = scope.enter_context(endpoint_slope())
                scope.callback(lambda: counters.update(counts))
            if mode == "endpoint-full":
                yield
                return
            prepare = localization_v3.prepare_tracks

            def stop_after_graph(*args, **kwargs):
                if profiler is None:
                    prepare(*args, **kwargs)
                else:
                    profiler.runcall(prepare, *args, **kwargs)
                raise GraphDone

            with patch.object(localization_v3, "prepare_tracks", stop_after_graph):
                yield

    try:
        replay("control", output, configure_solve=configure, result_details=receipt)
    except GraphDone:
        record = receipt()
        if profiler is not None:
            record["profile"] = attribution(profiler)
        write(output, record)
    else:
        if mode != "endpoint-full":
            raise ValueError("Expected graph-only preparation")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    parser.add_argument("--mode", choices=("profile", "original", "endpoint", "endpoint-full"), default="profile")
    trial(**vars(parser.parse_args()))
