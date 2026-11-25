"""Check the family-blind structural census and later owner-grade boundary."""

import json

import pytest

from opposite_radio_linear_support import census, grade


def point(radio, channel, start, positive=True):
    return dict(lane=(radio, channel), start=start, rf=channel, positive=positive)


def row(norad, observation, compatible):
    return dict(norad=norad, observation_ids=[observation], compatible=compatible, component=observation)


def fixture():
    opportunities = {"lost": point(2, 8, 0), "retained": point(1, 6, 0),
                     "wrong_bank": point(1, 1, 10), "empty": point(1, 6, 11, False)}
    opposite = {str(i): point(1, 6, i) for i in range(1, 7)}
    second = [row(101, "lost", False), row(102, "retained", True)]
    masks = {stage: dict(tracks=second) for stage in ("first", "after_salvage")}
    return opportunities | opposite, masks


def test_blind_census_counts_all_eligible_lanes_without_guessing_graph():
    result = census(*fixture())
    assert result["graph"] is None
    assert list(result["families"]) == [101]
    assert result["supported_banks"] == [(1, 1)]
    lost = result["families"][101]
    assert lost["opposite_positive_rows"] == 6
    assert lost["opposite_possible_components"] == 1


def test_only_complete_non_curved_opposite_track_can_be_eligible():
    opportunities, masks = fixture()
    track = dict(key="linear", receiver=1, curved=False, observation_ids=list("123456"))
    result = census(opportunities, masks, [track])
    assert result["families"][101]["eligible_linear_components"] == ["linear"]
    for altered in (dict(track, curved=True), dict(track, observation_ids=list("12345"))):
        result = census(opportunities, masks, [altered])
        assert result["families"][101]["eligible_linear_components"] == []


def test_post_seal_grade_separates_radio_feasibility_from_track_evidence():
    candidate = json.loads(json.dumps(census(*fixture())))
    gradebook = grade(candidate, {"1": (101, "predictive"), "2": (102, "predictive"),
                                  "3": (101, "predictive")}, {"3": (101, "predictive")})
    assert gradebook["opposite_radio"] == 1
    first, second = gradebook["rows"]
    assert first["opposite_radio"] and first["exact_eligible"] is None
    assert second["opposite_radio"] is None


def test_reject_inconsistent_gate_lane_metadata():
    opportunities, masks = fixture()
    opportunities["lost"]["positive"] = False
    with pytest.raises(ValueError, match="single signed physical lane"):
        census(opportunities, masks)
