"""Reuse a certified negative regional decision within one short pipeline solve."""

from contextlib import contextmanager
from copy import deepcopy
from time import process_time
from unittest.mock import patch


CERTIFICATES = frozenset(("inside_score", "ineligible_exterior_score", "eligible_exterior_tie",
                          "eligible_exterior_separation"))


def graph_inputs(graph):
    """Copy the mutable original observations and track fields read by the veto."""
    import numpy as np

    def array_key(values):
        array = np.asarray(values)
        return array.shape, array.dtype.str, array.tobytes()

    return (graph["metadata"]["causal_cutoff_utc_ns"], graph["metadata"]["anchor_utc_ns"],
            tuple((row["observation_id"], row["receiver"]) for row in graph["observations"]),
            tuple((track["key"], track["receiver"], track["rf_hz"], tuple(track["observation_ids"]),
                   array_key(track["times"]), array_key(track["values"])) for track in graph["tracks"]))


def cached(evaluate, audit, enabled):
    entry = None

    def score(graph, catalogue, region):
        nonlocal entry
        start = process_time()
        audit["requests"] += 1
        if enabled and entry is not None:
            old_graph, old_catalogue, old_region, inputs, answer = entry
            if old_graph is graph and old_catalogue is catalogue and old_region is region and graph_inputs(graph) == inputs:
                audit["hits"] += 1
                audit["lookup_cpu_s"] += process_time() - start
                return deepcopy(answer)
        audit["lookup_cpu_s"] += process_time() - start
        start = process_time()
        result = evaluate(graph, catalogue, region)
        audit["scorer_cpu_s"] += process_time() - start
        audit["scored_points"] += result["probes_evaluated"]
        entry = None
        if (enabled and result.get("complete") is False and result.get("would_withhold") is False
                and result.get("stop") in CERTIFICATES):
            start = process_time()
            entry = graph, catalogue, region, graph_inputs(graph), deepcopy(result)
            audit["lookup_cpu_s"] += process_time() - start
        return result

    return score


@contextmanager
def projection(original, audit, enabled, *libraries):
    from tools.pipeline_eval.variants.experimental import regional_reassignment

    with original(*libraries) as counts:
        wrapper = cached(regional_reassignment.evaluate_veto, audit, enabled)
        with patch.object(regional_reassignment, "evaluate_veto", wrapper):
            yield counts
