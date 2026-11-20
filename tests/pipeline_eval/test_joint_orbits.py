from types import SimpleNamespace

import numpy as np

from tools.pipeline_eval.variants import joint_orbits as solver


def arc(lane=0, rf=11.0e9, start=0, orbits=(0, 1)):
    values = np.arange(start, start + 4, dtype=float)
    track = SimpleNamespace(lane=lane, rf=rf, t=values)
    return SimpleNamespace(track=track, orbit=np.array(orbits))


def test_pair_move_can_find_a_shared_phase_missed_by_independent_arc_choices():
    arcs = [arc(), arc(lane=1, orbits=(0, 2))]
    matches = [
        (solver.Match(0, (9.0, 3.0, 1.0), 0), solver.Match(1, (1.0, 0.0, 1.0), 0)),
        (solver.Match(0, (9.0, 3.0, 1.0), 0), solver.Match(2, (1.0, 0.0, 1.0), 0)),
    ]
    rows, pair_moves = solver.associate(arcs, matches, 6.25)
    assert pair_moves == 1
    assert [row.orbit for row in rows] == [0, 0]
    assert solver.phase_cost((9.0, 3.0, 1.0)) > solver.phase_cost((1.0, 0.0, 1.0))


def test_simultaneous_arcs_can_select_distinct_satellites_and_reject_outlier():
    arcs = [arc(), arc(), arc(orbits=(2,))]
    matches = [
        (solver.Match(0, (0.2, 0.0, 1.0), 0), solver.Match(1, (3.0, 0.0, 1.0), 0)),
        (solver.Match(0, (3.0, 0.0, 1.0), 0), solver.Match(1, (0.2, 0.0, 1.0), 0)),
        (solver.Match(2, (200.0, 0.0, 1.0), 0),),
    ]
    rows, pair_moves = solver.associate(arcs, matches, 6.25)
    assert pair_moves == 0
    assert [row.orbit for row in rows] == [0, 1]


def test_phase_profile_respects_bound_and_outlier_has_no_orbit():
    bound = solver.lean.PHASE_BOUND_S
    assert np.isclose(
        solver.phase_cost((400.0, 20.0, 1.0)),
        (20.0 - bound) ** 2 + solver.PRIOR * bound**2,
    )
    result = solver.infer({"duration_s": 300, "tracks": []}, {"center": [1, 2]}, "")
    assert result["status"] == "withheld"
    assert all(arm["latlon"] is None for arm in result["arms"].values())


def test_profile_uses_same_folded_carrier_and_phase_scale_as_the_original_tracker():
    t = np.arange(4, dtype=float)
    sensitivity = np.array([0.0, 2.0, -2.0, 1.0])
    track = SimpleNamespace(t=t, lane=0, rf=11.5e9, drift=np.zeros(4), whiten=np.eye(4))
    candidate = SimpleNamespace(
        track=track,
        orbit=np.array([0]),
        phase=sensitivity[None, :],
        xy=np.zeros((1, 4, 2)),
        residual=(solver.lean.PERIOD + 3 * sensitivity)[None, :],
    )
    state = solver.lean.State(np.zeros(2), np.zeros(4), np.zeros(4), np.array([3.0]))
    (outcome,) = solver._matches(candidate, state)
    assert outcome.alias == 1
    assert np.allclose(outcome.stats, (81.0, 27.0, 9.0))
