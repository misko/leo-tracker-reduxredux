"""C-arm ownership and coherent source-group proposal invariants."""

import importlib
import sys
from pathlib import Path

import numpy as np
import pytest


@pytest.fixture
def tool():
    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))
    try:
        yield importlib.import_module("iterate_dsx01_integrated_labels")
    finally:
        sys.path.pop(0)


def test_acceptance_uses_c0_and_keeps_its_exact_partner(tool):
    old = dict(c0=dict(score=20), fitted_c=dict(score=1))
    new = dict(c0=dict(score=17), fitted_c=dict(score=500))
    accepted, gain = tool.accept_pair(old, new)
    assert accepted is new and accepted["fitted_c"] is new["fitted_c"] and gain == 3


def test_fitted_c_gain_alone_cannot_accept_a_proposal(tool):
    old = dict(c0=dict(score=20), fitted_c=dict(score=100))
    new = dict(c0=dict(score=20 - 1e-8), fitted_c=dict(score=1))
    assert tool.accept_pair(old, new) == (old, 0.0)


def test_group_change_preserves_points_and_incumbent_and_existing_shared_phase(tool):
    original = dict(
        rows=[
            dict(candidate_index=0, candidate_norad=100, component="a"),
            dict(candidate_index=0, candidate_norad=100, component="b"),
            dict(candidate_index=1, candidate_norad=101, component="c"),
        ],
        state=dict(
            beta=np.zeros(8), phases=np.array([2.0, 3.0, 4.0]), extra={}, smooth=np.zeros((2, 3))
        ),
    )
    changed = tool.changed_seed(
        original, [dict(group=[0, 1], new=1)], np.array([8.0, 9.0, 10.0]), np.array([100, 101, 102])
    )
    assert [r["candidate_index"] for r in changed["rows"]] == [1, 1, 1]
    assert [r["component"] for r in changed["rows"]] == ["a", "b", "c"]
    assert changed["state"]["phases"][1] == 3.0
    assert [r["candidate_index"] for r in original["rows"]] == [0, 0, 1]
    changed["state"]["beta"][0] = 99
    assert original["state"]["beta"][0] == 0
