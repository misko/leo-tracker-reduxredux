from pathlib import Path
import sys
from types import SimpleNamespace

import numpy as np
import pytest


RESEARCH = Path(__file__).resolve().parents[2] / "reports/ALGO08/v3"
sys.path.insert(0, str(RESEARCH))
try:
    from fixed_causal_estimation import flatten, overlap, restriction, retained_members
finally:
    sys.path.remove(str(RESEARCH))


def test_only_original_owned_rows_enter_the_fixed_causal_fit():
    before = {"curved": ("conditional", 2, frozenset(("a", "b"))),
              "linear": ("predictive", 2, frozenset(("c", "d")))}
    selected = retained_members(before, {"a", "c", "unowned"})
    assert flatten(selected) == [("a", 2, "conditional"), ("c", 2, "predictive")]
    assert flatten(before) == [("a", 2, "conditional"), ("b", 2, "conditional"),
                               ("c", 2, "predictive"), ("d", 2, "predictive")]
    assert overlap(flatten(selected), [("a", 3, "predictive"), ("new", 2, "predictive")]) == dict(
        left=2, right=2, common=1, left_only=1, right_only=1, norad_changed=1, role_changed=1)


def test_restriction_preserves_curved_design_and_predictive_alias_values_and_basis():
    times = np.array([10., 11., 12.])
    values = np.array([11000., 10500., 10000.])
    geometry = np.arange(6).reshape(3, 2)
    conditional = dict(key="curve", observation_ids=["a", "b", "old-reject"], times=times, values=values)
    predictive = dict(key="line", observation_ids=["c", "d", "e"], times=times, values=values)
    constant = {"shared": 150.}
    scan = SimpleNamespace(tracks=[conditional, predictive], white=[None, None], rx_basis=[geometry, geometry],
                           index=[np.arange(3), np.arange(3)], fixed_window_noise=constant)
    entry = dict(track_index=1, component="line", alias=-1, norad=25, points=3,
                 observation_ids=predictive["observation_ids"])
    node = dict(seed=dict(rows=[dict(active_curvature=True, component="curve")]), aliases=[1])
    signed = dict(scan=scan, node=node, keep=np.array([True, True, False]), entries=[entry], powers=[.5])
    members = {"curve": ("conditional", 25, frozenset(("a", "b"))),
               "line": ("predictive", 25, frozenset(("c", "d", "e")))}
    causal = {"b", "c", "e", "old-reject"}
    reduced = restriction(signed, members, causal)
    assert reduced["scan"].tracks[0] is conditional
    assert reduced["scan"].fixed_window_noise is constant
    assert reduced["node"] is node and reduced["powers"] is signed["powers"]
    np.testing.assert_array_equal(reduced["keep"], [False, True, False])
    assert reduced["scan"].tracks[1]["observation_ids"] == ["c", "e"]
    np.testing.assert_array_equal(reduced["scan"].tracks[1]["values"], values[[0, 2]])
    np.testing.assert_array_equal(reduced["scan"].rx_basis[1], geometry[[0, 2]])
    assert reduced["entries"][0] == dict(entry, observation_ids=["c", "e"], points=2)
    assert scan.tracks[1] is predictive and entry["points"] == 3

    corrupted = dict(members, curve=("conditional", 25, frozenset(("old-reject",))))
    with pytest.raises(ValueError, match="activated a formerly rejected row"):
        restriction(signed, corrupted, causal)
