from copy import deepcopy

import pytest

from mixture_track_attribution import attribute_positions


def point(joint0, joint1):
    tracks = []
    for tid, weight, joint in (("a", 1, joint0), ("b", 3, joint1)):
        scores = {"D": 2., "D_plus_detection": 3., "D_plus_geometry": joint}
        tracks.append({"track_id": tid, "weight_seconds": weight, "candidate_ids": [10, 20],
                       "variants": {"mixture": {"scores": scores,
                           "frequency_map_candidate_id": 10, "joint_map_candidate_id": 10}}})
    return {"weight_seconds": 4, "tracks": tracks, "variant_scores": {"mixture": {
        "D": 2., "D_plus_detection": 3., "D_plus_geometry": (joint0 + 3 * joint1) / 4}}}


def test_duration_weighted_additivity_and_map_change_attribution():
    left, right = point(4., 4.), point(3., 5.)
    right["tracks"][0]["variants"]["mixture"]["joint_map_candidate_id"] = 20
    result = attribute_positions(left, right)
    assert result["total_score_change"]["joint"] == .5
    assert result["total_score_change"]["ratio_increment"] == .5
    assert result["joint_score_change_by_joint_map_change"] == {"changed": -.25, "unchanged": .75}
    assert result["association_change_counts"]["joint_map_changed"] == 1


def test_candidate_order_does_not_count_as_shortlist_change():
    left, right = point(4., 4.), point(4., 4.)
    right["tracks"][0]["candidate_ids"].reverse()
    assert attribute_positions(left, right)["association_change_counts"]["shortlist_changed"] == 0


@pytest.mark.parametrize("mutation", ["duplicate", "weight", "score", "nan"])
def test_rejects_incomparable_or_inconsistent_positions(mutation):
    left, right = point(4., 4.), deepcopy(point(4., 4.))
    if mutation == "duplicate": right["tracks"][1]["track_id"] = "a"
    elif mutation == "weight": right["tracks"][0]["weight_seconds"] = 2
    elif mutation == "score": right["variant_scores"]["mixture"]["D_plus_geometry"] += .1
    else: right["tracks"][0]["variants"]["mixture"]["scores"]["D"] = float("nan")
    with pytest.raises(ValueError): attribute_positions(left, right)
