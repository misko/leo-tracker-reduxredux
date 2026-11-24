from itertools import product
from types import SimpleNamespace

import graph_half_blend_rank_trial as trial
import numpy as np
import pytest


def fixture():
    scan = SimpleNamespace(search_region=SimpleNamespace(half_width_km=12.5))
    centre = [dict(hypothesis=i, center_score=loss, seed={"state": object()}, family=family)
              for i, (loss, family) in enumerate(zip([3., 2., 2., 4.], [1, 2, 2, 3], strict=True))]

    def signature(node):
        return (("track", node["family"], 10 + node["family"], 0),)

    def fresh(scan, sigma, *, budget):
        for _ in range(2 * budget):
            discovery.explore(scan, None, (0, 0))
        return centre

    discoveries = iter([3, 4, 1, 4])

    def explore(scan, state, offset):
        return dict(family=next(discoveries)) if offset != (0, 0) else None

    class Normal:
        def __init__(self, node):
            self.node = node

        def residual(self, point):
            return np.array([1. if self.node["family"] in (1, 4) else 2.])

    discovery = SimpleNamespace(fresh_discovery=fresh, explore=explore, signature=signature)
    position = SimpleNamespace(NormalPosition=Normal)

    def rank(scan):
        seeds = discovery.fresh_discovery(scan, 1., budget=4)
        parent = min(seeds, key=lambda node: node["center_score"])
        nodes = seeds + [discovery.explore(scan, parent["seed"]["state"], point)
                         for point in product((-12.5, 12.5), repeat=2)]
        earliest = {}
        for node in nodes:
            earliest.setdefault(discovery.signature(node), node)
        return sorted(earliest.values(), key=lambda node: np.linalg.norm(Normal(node).residual([0, 0])))

    return rank, scan, discovery, position


def test_full_trace_reads_first_seen_corner_order_and_exact_ties():
    rank, scan, discovery, position = fixture()
    original = discovery.signature
    trace = trial.rank_trace(rank, scan, discovery, position)
    assert discovery.signature is original
    assert trace["counts"] == dict(centres=4, corners=4, internal_centre_explorations=8,
                                   distinct=4, score_calls=4)
    assert [row["corner_parent"] for row in trace["centres"]] == [False, True, False, False]
    assert [row["first_proposal"] for row in trace["ordered"]] == [0, 5, 1, 3]
    assert trace["ordered"][0]["loss"]["binary64"] == (1.).hex()
    assert trace["exact_ties"] == [[1, 2], [3, 4]]


def test_distinguishes_reorder_from_a_new_top_three_member():
    trace = trial.rank_trace(*fixture())
    a, b, c, d = trace["ordered"]
    order = trial.top_three(trace, dict(ordered=[b, a, c, d]))
    assert order["same_members"] and not order["same_order"] and order["shared"] == 3
    changed = trial.top_three(trace, dict(ordered=[b, a, d, c]))
    assert not changed["same_members"] and not changed["same_order"] and changed["shared"] == 2


def test_refuses_an_unobserved_reorder_and_restores_original_ports():
    rank, scan, discovery, position = fixture()
    original = position.NormalPosition.residual
    with pytest.raises(ValueError, match="original producer return"):
        trial.rank_trace(lambda scan: list(reversed(rank(scan))), scan, discovery, position)
    assert position.NormalPosition.residual is original
