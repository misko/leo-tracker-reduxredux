from importlib import import_module
from pathlib import Path
from contextlib import nullcontext
from types import SimpleNamespace

import numpy as np
import pytest


@pytest.fixture
def rank(monkeypatch):
    directory = Path(__file__).resolve().parents[2] / "reports/ALGO08/v3"
    monkeypatch.syspath_prepend(str(directory))
    return import_module("proof_global_rank")


def test_owner_union_uses_original_index_order_and_falls_back_if_unusable(rank):
    catalogue = [9, 4, 15, 30, 1, 7, 2, 13, 12, 11]
    probes = [{"owners": dict(enumerate([13, 7, 9, 4, 15, 1, 2, 11, None, 100]))}]
    assert rank.select_pool(probes, catalogue) == [0, 1, 2, 4, 5, 6, 7, 9]
    assert rank.select_pool([], catalogue) is None
    assert rank.select_pool([{"owners": {0: 13}}], catalogue) is None
    assert rank.select_pool([{"owners": dict(enumerate(catalogue))}], catalogue) is None


def test_fallback_for_ties_at_and_before_the_finalist_cut(rank):
    assert rank.fallback_reason([(1., {}), (2., {}), (3., {}), (3., {})]) == "rank_tie"
    assert rank.fallback_reason([(1., {}), (1., {}), (3., {})]) == "rank_tie"
    assert rank.fallback_reason([(1., {}), (2., {})]) == "insufficient_finite_finalists"
    assert rank.fallback_reason([(1., {}), (2., {}), (3., {}), (4., {})]) is None


def test_rank_comparison_detects_order_and_signed_roll_changes(rank):
    stock = [dict(score=score, owners=[("track", norad, alias)])
             for score, norad, alias in [(1., 10, -1), (2., 11, 0), (3., 12, 1)]]
    result = rank.compare_top_three(stock, stock)
    assert result["ordered_assignments"] and result["within_score_tolerance"]
    wrong_alias = [dict(stock[0], owners=[("track", 10, 1)]), *stock[1:]]
    result = rank.compare_top_three(stock, wrong_alias)
    assert not result["ordered_assignments"] and result["within_score_tolerance"]
    result = rank.compare_top_three(stock, stock[::-1])
    assert not result["ordered_assignments"] and not result["within_score_tolerance"]


def test_reduced_nominee_is_restored_to_full_original_index_space(rank):
    full = import_module("proof_global_short_trial")
    scan = SimpleNamespace(norads=np.array([11, 20, 32, 48]), rx_basis=[np.zeros((2, 4))])
    candidate = dict(seed={"rows": [dict(candidate_index=1, candidate_norad=48)]}, aliases=[-1])
    node, = full.expand_nodes(scan, [0, 3], [(1., candidate)])
    assert node["seed"]["rows"] == [dict(candidate_index=3, candidate_norad=48)]
    assert len(node["seed"]["state"]["phases"]) == 4
    assert node["aliases"] == [-1]
    assert candidate["seed"]["rows"][0]["candidate_index"] == 1


def test_live_empty_proof_invokes_the_ordinary_full_route(rank):
    full = import_module("proof_global_short_trial")
    scan, audit, calls = SimpleNamespace(norads=np.array([1, 2, 3])), [], []

    def ordinary(value):
        calls.append(value)
        return ["full cold nodes"]

    assert full.rank_live([], audit, ordinary, scan, None, None, None, lambda _: nullcontext()) == ["full cold nodes"]
    assert calls == [scan]
    assert audit[0]["fallback"] == "unusable_proof_pool" and audit[0]["original_orbits"] == 3
