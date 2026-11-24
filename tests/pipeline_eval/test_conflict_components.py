import numpy as np

from reports.ALGO08.v3.conflict_components import branch_support, exclusive_edges, joined_sizes, topology
from reports.ALGO08.v3.conflict_component_trial import ExactStates


def track(receiver, start, end, ids):
    return dict(receiver=receiver, channel=1, rf_hz=11.6e9, start_s=start, end_s=end, observation_ids=ids)


def test_observation_conflicts_are_exclusive_and_retain_isolated_models():
    support = {0: [3, 3, 9], 1: [9, 8], 2: [8], 3: [4]}
    edges = exclusive_edges(support)
    assert edges == {(0, 1), (1, 2)}
    assert joined_sizes(support, edges) == [3, 1]


def test_satellite_alias_and_shared_phase_extend_different_dependency_scopes():
    tracks = [track(1, 1, 4, [1]), track(2, 3, 5, [2]), track(2, 8, 9, [3]), track(1, 8, 9, [4])]
    result = topology(tracks, {"0": [(9, 1)], "1": [(9, 2)], "2": [(9, 1)], "3": [(10, 1)]})
    assert result["same_observation_edges"] == 0
    assert result["overlapping_same_alias_edges"] == 0
    assert result["overlapping_different_alias_edges"] == 1
    assert result["components"]["local"] == [2, 1, 1]
    assert result["components"]["shared_phase"] == [3, 1]
    assert result["components"]["common_position"] == [4]


def test_repeated_label_is_not_exact_repeated_work_when_state_or_base_changes():
    clock = ExactStates()
    state = {key: np.zeros(2) for key in ("beta", "phases", "smooth")} | {"extra": {}}
    base = (np.zeros((2, 2)),)
    assert not clock.repeated(state, base, (0, 0), "receiver_smooth", False)
    assert clock.repeated(state, base, (0, 0), "receiver_smooth", False)
    state["beta"][0] = 1.0
    assert not clock.repeated(state, base, (0, 0), "receiver_smooth", False)
    assert not clock.repeated(state, (base[0].copy(),), (0, 0), "receiver_smooth", False)


def test_later_owner_can_be_retained_only_by_gate_independent_nomination():
    tracks = [track(1, 0, 2, ["a"]), track(2, 1, 4, ["b"])]
    stages = [{"curves": [dict(track=0, gated=[(20, -1)], nominee=(21, 2)),
                          dict(track=1, gated=[], nominee=None)]}]
    switches = {"a": (20, 21, "conditional"), "b": (20, 21, "predictive")}
    first, second = branch_support(tracks, stages, switches)
    assert first["gated"] == [(20, -1)]
    assert first["nominated"] == [(21, 2)]
    assert first["both_in_same_pass"] == 1
    assert second["changed_observations"] == 1 and not second["gated"] and not second["nominated"]
