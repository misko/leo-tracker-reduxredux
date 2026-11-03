import importlib.util
from pathlib import Path

import numpy as np
import pytest

SPEC = importlib.util.spec_from_file_location(
    "identity_audit", Path(__file__).with_name("audit.py")
)
audit = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(audit)


def fixture():
    times = [0.0, 0.2, 0.4, 0.6, 2.0, 2.2]
    metadata = [
        dict(observation_id=str(i), time_s=t, receiver=1, channel=4, actual_rf_hz=11e9)
        for i, t in enumerate(times)
    ]
    state = dict(
        associated=np.array([True, True, False, True, True, True]),
        satellite_number=np.array([7, 7, 999, 8, 7, 7]),
        times_s=np.array(times),
    )
    return state, metadata


def test_counts_keep_unassigned_denominator_and_do_not_claim_truth():
    state, metadata = fixture()
    result = audit.window_stats(state, range(6), metadata)
    assert result["observations"] == 6 and result["assigned"] == 5
    assert result["model_id_counts"] == {"7": 4, "8": 1}
    assert result["dominant_count"] == 4 and result["dominant_fraction_of_all"] == 4 / 6
    assert result["dominant_fraction_of_assigned"] == 4 / 5
    assert result["ids_with_at_least_3_assignments"] == 1


def test_switches_do_not_bridge_unassigned_or_large_gaps_or_different_lanes():
    state, metadata = fixture()
    result = audit.window_stats(state, range(6), metadata)
    assert result["adjacent_assigned_comparisons"] == 2
    assert result["adjacent_identity_switches"] == 0
    assert result["adjacency_exclusions"] == {"unassigned_endpoint": 2, "gap_above_limit": 1}
    state["satellite_number"][1] = 8
    assert audit.window_stats(state, range(6), metadata)["adjacent_identity_switches"] == 1
    metadata[1]["actual_rf_hz"] += 1
    result = audit.window_stats(state, range(6), metadata)
    assert result["adjacent_identity_switches"] == 0
    assert result["adjacency_exclusions"]["different_lane"] == 1


def test_all_lost_points_stay_in_denominator_and_restoration_is_net():
    state, metadata = fixture()
    original = audit.window_stats(state, range(6), metadata)
    state["associated"][:] = False
    result = audit.window_stats(state, range(6), metadata)
    assert result["observations"] == 6 and result["unassigned"] == 6
    assert result["dominant_model_id"] is None
    assert result["dominant_fraction_of_all"] == 0
    assert result["dominant_fraction_of_assigned"] is None
    assert audit.comparison(original, result)["net_assigned_gain"] == -5
    assert not audit.comparison(original, result)["strong_restoration_descriptive"]


def test_alignment_checks_explicit_ids_and_source_order():
    state, metadata = fixture()
    audit.validate_alignment(state, metadata)
    state["observation_id"] = np.array([r["observation_id"] for r in metadata])
    state["observation_id"][[0, 1]] = state["observation_id"][[1, 0]]
    with pytest.raises(AssertionError):
        audit.validate_alignment(state, metadata)
    del state["observation_id"]
    state["times_s"] = state["times_s"][::-1]
    with pytest.raises(AssertionError):
        audit.validate_alignment(state, metadata)


def test_invalid_membership_and_empty_window():
    state, metadata = fixture()
    with pytest.raises(ValueError):
        audit.window_stats(state, [0, 0], metadata)
    result = audit.window_stats(state, [], metadata)
    assert result["observations"] == 0 and result["adjacent_identity_switches"] == 0
    assert result["dominant_fraction_of_all"] is None
