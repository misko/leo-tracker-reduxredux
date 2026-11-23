from importlib import import_module
from pathlib import Path

import numpy as np
import pytest


@pytest.fixture
def selectors(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / "reports/ALGO08/v3"))
    return import_module("arc_design")


def test_divide_nuisance_only_if_block_local(selectors):
    global_term = np.array([[0.2, 0.4, 0.6], [0.3, 3.0, 0.5], [0.9, 0.1, 0.3], [1.4, 1.2, 1.1]])
    local_term = np.array([[1.], [2.], [3.], [4.]])
    separately = sum(selectors.profile(d.T @ d, 3)
                     for d in (np.c_[global_term[:2], local_term[:2]], np.c_[global_term[2:], local_term[2:]]))
    joint = np.column_stack((global_term, np.r_[local_term[:2, 0], 0., 0.], np.r_[0., 0., local_term[2:, 0]]))
    direct = selectors.profile(joint.T @ joint, 2, unpenalized=1)
    shared_once = selectors.profile(separately, 2, unpenalized=1)
    independent_clock = sum(selectors.profile(d.T @ d, 2, unpenalized=1)
                            for d in (np.c_[global_term[:2], local_term[:2]], np.c_[global_term[2:], local_term[2:]]))
    assert np.allclose(shared_once, direct)
    assert not np.allclose(shared_once, independent_clock)


def test_minimum_cost_uses_lane_union_and_matched_arm_fraction(selectors):
    def block(norad, lanes, coverage, c0, fit):
        return selectors.Block(norad, frozenset(lanes), frozenset(coverage),
                               tuple(np.diag([east, north, 1.]) for east, north in (c0, fit)))

    east = block(1, (1, 2, 3), ("rx1", "time1"), (10, 0), (10, 0))
    north = block(2, (2, 3, 4), ("rx2", "time2"), (0, 10), (0, 10))
    redundant = block(3, (5, 6), ("rx2", "time2"), (.5, .5), (.5, 2))
    rows = selectors.select([east, north, redundant], 18)
    cap = rows["frontier"]["3"]
    assert cap["best"]["lanes"] == 6
    assert cap["target"]["norads"] == (1, 2, 3)
    assert cap["target"]["lanes"] == 6
    assert selectors.select([east, north], 12)["frontier"]["3"]["target"]["lanes"] == 4
    known = selectors.select([east, north], 18, authority=[east, north, redundant])["frontier"]["3"]
    assert known["target"] is None
    assert known["best"]["per_arm"] == pytest.approx((10 / 10.5, 10 / 12))
    assert known["best"]["fraction"] <= known["optimistic_upper"] + 1e-12
    assert rows["frontier"]["12"]["selected"] is None


def test_relaxed_directional_bound_dominates_exhaustive_overlapping_sets(selectors):
    rng = np.random.default_rng(708)
    for _ in range(6):
        blocks = []
        for norad in range(6):
            lanes = frozenset(rng.choice(26, size=6, replace=False))
            linear = [rng.normal(size=(8, 5)) for _ in selectors.ARMS]
            grams = tuple(rows.T @ rows for rows in linear)
            blocks.append(selectors.Block(norad, lanes, frozenset({"all"}), grams))
        plan = selectors.select(blocks, 66)
        for row in plan["frontier"].values():
            if row["best"] is not None:
                assert row["best"]["fraction"] <= row["optimistic_upper"] + 1e-10
