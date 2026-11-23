"""Scope the two reviewed exact optimizations to installed Graph preparation."""

from collections import Counter
from contextlib import ExitStack, contextmanager
from pathlib import Path
from time import perf_counter_ns, process_time_ns
from unittest.mock import patch


PINS = {
    "vector_graph_edges.py": "b4a4c67f9100b668129bce2c4baa23440edde92374386260475be01f898115fd",
    "polynomial_fit_cache.py": "6c2f936f9904c707a6dab7846fb242602baf72a369c1c207624825625906c75b",
}


@contextmanager
def graph_execution(*, enabled=False, audit=None):
    if not enabled and audit is None:
        yield
        return

    from leo.analysis import graph_tracklets as graph
    from leo.analysis.localization_v3 import tracks

    counts, cached = Counter(), Counter()
    original_graph, original_edges = tracks.graph_tracks, graph._graph
    with ExitStack() as scopes:
        if enabled:
            from empty_bootstrap import checked

            source = Path(__file__).resolve().parent
            for name, digest in PINS.items():
                checked(source / name, digest)
            import polynomial_fit_cache
            import vector_graph_edges

            for module in (polynomial_fit_cache, vector_graph_edges):
                expected = source / (module.__name__ + ".py")
                if Path(module.__file__).resolve() != expected:
                    raise ValueError("Exact Graph optimization did not load the reviewed source")
            scopes.enter_context(polynomial_fit_cache.reuse("best", cached))

        def fallback(t, y, cfg):
            counts["edge_fallbacks"] += 1
            return original_edges(t, y, cfg)

        def build(t, y, cfg):
            cpu, wall = process_time_ns(), perf_counter_ns()
            value = vector_graph_edges.ordered_edges(t, y, cfg, fallback) if enabled else original_edges(t, y, cfg)
            counts["edge_cpu_ns"] += process_time_ns() - cpu
            counts["edge_elapsed_ns"] += perf_counter_ns() - wall
            counts["edge_lanes"] += 1
            counts["edges"] += len(value[0])
            return value

        def graph_tracks(*args, **kwargs):
            cpu, wall = process_time_ns(), perf_counter_ns()
            value = original_graph(*args, **kwargs)
            counts["graph_cpu_ns"] += process_time_ns() - cpu
            counts["graph_elapsed_ns"] += perf_counter_ns() - wall
            counts["calls"] += 1
            counts["assigned"] += value[1]
            counts["tracks"] += len(value[0])
            return value

        scopes.enter_context(patch.object(graph, "_graph", build))
        scopes.enter_context(patch.object(tracks, "graph_tracks", graph_tracks))
        yield
    if audit is not None:
        audit.update(enabled=enabled, graph=dict(counts), cache=dict(cached), sources=PINS if enabled else {})
