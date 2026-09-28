from copy import deepcopy

import pytest

from dual_track_attribution import compare


def point():
    tracks = []
    for tid, weight in (("a", 2), ("b", 3)):
        scores = {"D": 1., "D_plus_detection": 2., "D_plus_geometry": 4.,
                  "D_plus_reversed_geometry": 5.}
        tracks.append({"track_id": tid, "weight_seconds": weight,
            "reserve_observations": 4, "candidate_ids": [10, 20],
            "training_prior": {"map_candidate_id": 10},
            "variants": {"dual": {"scores": scores, "frequency_map_candidate_id": 10,
                                   "joint_map_candidate_id": 20}}})
    return {"tracks": tracks, "weight_seconds": 5,
            "variant_scores": {"dual": dict(tracks[0]["variants"]["dual"]["scores"])}}


def test_exact_weighted_telescope_and_id_order_invariance():
    a = point(); b = deepcopy(a)
    b["tracks"][0]["candidate_ids"].reverse()
    b["tracks"][0]["variants"]["dual"]["scores"]["D_plus_geometry"] = 3.
    b["tracks"][0]["variants"]["dual"]["joint_map_candidate_id"] = 10
    b["variant_scores"]["dual"]["D_plus_geometry"] = 3.6
    result = compare(a, b)
    assert result["totals"]["delta_joint"] == pytest.approx(-.4)
    assert result["totals"]["delta_conditional_ratio_increment"] == pytest.approx(-.4)
    assert result["totals"]["delta_detection_increment"] == 0
    assert result["changes"]["shortlist_changed"] == 0
    assert result["changes"]["joint_map_changed"] == 1
    assert result["groups"]["joint_map_changed"]["delta_joint"] == pytest.approx(-.4)
    assert compare(a, a)["totals"]["delta_joint"] == 0


def test_rejects_inconsistent_aggregate():
    a = point(); b = deepcopy(a)
    b["tracks"][0]["variants"]["dual"]["scores"]["D"] += 1
    with pytest.raises(ValueError, match="reconstruct aggregate"):
        compare(a, b)


def test_rejects_missing_track_even_with_adjusted_aggregate_weight():
    a = point(); b = deepcopy(a); b["tracks"].pop(); b["weight_seconds"] = 2
    with pytest.raises(ValueError, match="inventory"):
        compare(a, b)


def test_rejects_reserve_change():
    a = point(); b = deepcopy(a); b["tracks"][0]["reserve_observations"] += 1
    with pytest.raises(ValueError, match="reserve"):
        compare(a, b)
