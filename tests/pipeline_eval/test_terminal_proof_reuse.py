from pathlib import Path
import sys

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "reports/ALGO08/v3"))
from terminal_proof_reuse import cached


def fixture(stop="inside_score", complete=False):
    audit = dict(requests=0, hits=0, scored_points=0, scorer_cpu_s=0., lookup_cpu_s=0.)
    graph = dict(metadata=dict(anchor_utc_ns=0, causal_cutoff_utc_ns=0),
                 observations=[dict(observation_id="a", receiver=0)],
                 tracks=[dict(key="k", receiver=0, rf_hz=109e8, observation_ids=["a"],
                              times=np.array([.5]), values=np.array([12.]))])

    def score(*args):
        return dict(would_withhold=complete, complete=complete, stop=stop, probes_evaluated=25, detail=[1])

    return cached(score, audit, True), audit, graph, object(), object()


def test_reuse_requires_same_objects_and_unmodified_graph_and_returns_an_owned_result():
    score, audit, graph, catalogue, region = fixture()
    score(graph, catalogue, region)["detail"].append(2)
    assert score(graph, catalogue, region)["detail"] == [1]
    graph["tracks"][0]["values"][0] += 1
    score(graph, catalogue, region)
    score(graph, object(), region)
    score(graph, catalogue, object())
    assert audit["hits"] == 1 and audit["scored_points"] == 100


@pytest.mark.parametrize("reason,complete", [("invalid_score", False), ("inside_score", True), ("invalid_layout", False)])
def test_diagnostic_errors_and_completed_checks_are_always_recomputed(reason, complete):
    score, audit, *args = fixture(reason, complete)
    score(*args)
    score(*args)
    assert audit["hits"] == 0 and audit["scored_points"] == 50
