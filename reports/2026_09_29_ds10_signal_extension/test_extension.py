"""Scientific admission tests independent of storage, hardware and known words."""

import importlib.util
from pathlib import Path

SPEC = importlib.util.spec_from_file_location(
    "ds10_associations", Path(__file__).with_name("associations.py")
)
associations = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(associations)


def candidate(**changes):
    return dict({
        "abstention_recommended": False, "leading_candidate_persisted_on_heldout": True,
        "training_leader_heldout_rank": 1, "leading_catalog_number": 123,
        "nominal_heldout_negative_log_score": 10,
        "radio_null_heldout_negative_log_score": 11,
        "wrong_time_minus_500_heldout_negative_log_score": 12,
        "wrong_time_plus_500_heldout_negative_log_score": 13,
        "tracklet_ids": ["track"], "physical_group_id": "group",
    }, **changes)


def test_all_controls_must_be_beaten():
    assert associations.candidate_tier(candidate()) == "control_supported_candidate"
    for value in [None, 9, 10]:
        assert associations.candidate_tier(candidate(
            radio_null_heldout_negative_log_score=value
        )) == "heldout_candidate"


def test_no_label_for_abstention_or_nonpersistent_leader():
    assert associations.candidate_tier(candidate(abstention_recommended=True)) is None
    assert associations.candidate_tier(candidate(training_leader_heldout_rank=2)) is None


def test_conflicting_exact_track_labels_abstain():
    result = associations.bind_candidates({"tle_candidates": [
        candidate(), candidate(leading_catalog_number=456),
    ]})
    assert result["track"]["norad_id"] is None
    assert result["track"]["tier"] == "conflicting_candidates"


def test_full_sequence_bridge_distinguishes_interior_observations():
    spec = importlib.util.spec_from_file_location(
        "ds10_bridge", Path(__file__).with_name("bridge.py")
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    base = module.signature(0, 1, 11e9, [1, 2, 3], [1, 2, 3], [100, 200, 300])
    assert base != module.signature(0, 1, 11e9, [1, 4, 3], [1, 2, 3], [100, 200, 300])
    assert base != module.signature(0, 1, 11e9, [1, 2, 3], [1, 2, 3], [100, 201, 300])
    assert base != module.signature(0, 1, 11e9, [1, 2, 3], [1, 2.000000001, 3],
                                    [100, 200, 300])


def test_duplicate_visit_selection_uses_quality_not_identity():
    spec = importlib.util.spec_from_file_location(
        "ds10_compare", Path(__file__).with_name("compare.py")
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    row = dict(session="s", visit=1, receiver=0, channel=2, edge="upper", pilot=.6)
    rows = [row, dict(row, pilot=.7, norad_id=999), dict(row, visit=2)]
    assert module.unique_visits(rows) == [1, 2]
    assert module.time_bin(599) == 0
    assert module.time_bin(600) == 1
    assert module.time_bin(7200) == 2
