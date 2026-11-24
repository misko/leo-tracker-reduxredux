from copy import deepcopy
from pathlib import Path

import pytest

from reports.ALGO08.v3.single_rank_refusal_trial import compare, find_rank


def test_rank_readout_resolves_the_exact_original_through_nested_wrappers():
    def ranked_initial_nodes(scan):
        return scan

    def wrap(original):
        def rank(scan):
            return original(scan)
        return rank

    operation = wrap(wrap(ranked_initial_nodes))
    _, installed = find_rank(operation, Path(__file__))
    assert installed is ranked_initial_nodes
    with pytest.raises(ValueError, match="Unsupported exact rank wrapper"):
        find_rank(operation, Path("/missing"))


def test_comparison_catches_rank_or_checkpoint_difference():
    nodes = [dict(score="0x1.0p+2", signature=["A"]), dict(score="0x1.0p+3", signature=["B"])]
    scout = {"fallback": "no_supported_scout"}
    ordinary = dict(clock={"cpu_ns": 20, "elapsed_ns": 21}, scopes={"two_centre_rank": scout,
                    "nomination_handoff": {"prefixes_captured": 2}}, calls=[nodes, nodes], region="offer",
                    prepared_geometry_sha256="geometry", winner=["A"], endpoint=[0, 1], reference=[0.],
                    finalist_evidence={"scores": [4, 8]}, checkpoint=[["A"], ["B"]], tracked_owner_signature=[["A"], ["B"]])
    fixed = deepcopy(ordinary)
    fixed["scopes"]["two_centre_rank"]["declined_before_centre_fits"] = True
    fixed["calls"] = [deepcopy(nodes)]
    fixed["clock"] = {"cpu_ns": 10, "elapsed_ns": 11}
    pairs = [{"ordinary": ordinary, "fixed": fixed}]*2
    prior = {"lean_attempts": [{"cold": {"scores": [4, 8], "cpu_ns": 200}}],
             "two_centre_rank": {"finalist_signatures": [["A"], ["B"]]}}
    assert compare(pairs, prior)["median_cold_saved_ns"] == {"cpu_ns": 10, "elapsed_ns": 10}
    fixed["calls"][0][0]["score"] = "0x1.1p+2"
    with pytest.raises(ValueError, match="one exact rank"):
        compare(pairs, prior)
    fixed["calls"][0][0]["score"] = nodes[0]["score"]
    fixed["checkpoint"][0] = ["B"]
    with pytest.raises(ValueError, match="checkpoints failed"):
        compare(pairs, prior)
