import copy

import pytest

from shared_geometry_reporting import summarize, validate_branch, VARIANTS


def rows():
    return [{"session_id": str(i), "prior": p,
             "errors_km": {"D": 4., "old": 3., "mixture": 5., "shared": 3.}}
            for i in range(4) for p in ("sacramento", "reno")]


def test_complete_cohort_and_comparison_counts():
    result = summarize(rows(), list(map(str, range(4))))
    assert result["combined"]["shared_vs"]["D"]["improved"] == 8
    assert result["reno"]["shared_vs"]["old"]["tied"] == 4
    assert result["sacramento"]["mean_error_km"]["shared"] == 3.


@pytest.mark.parametrize("mutation", ["missing", "duplicate", "nan", "negative"])
def test_invalid_cohort_rejected(mutation):
    data = copy.deepcopy(rows())
    if mutation == "missing": data.pop()
    elif mutation == "duplicate": data.append(data[0])
    elif mutation == "nan": data[0]["errors_km"]["shared"] = float("nan")
    else: data[0]["errors_km"]["shared"] = -1.
    with pytest.raises(ValueError): summarize(data, list(map(str, range(4))))


def branch_fixture():
    points = [{"east_km": float(i), "north_km": 0., "latitude_deg": 37.,
               "longitude_deg": -122. + i / 100.,
               "scores": {"D": float(i + 1), "D_plus_geometry": float(2 - i)}}
              for i in range(2)]
    saved = {"grid_count": 2, "point_components": points,
             "arms": {"D": {"selected": {**points[0], "tracks": []}},
                      "D_plus_geometry": {"selected": {**points[1], "tracks": []}}}}
    evaluated = [{**{k: v for k, v in p.items() if k != "scores"},
                  "variant_scores": {v: dict(p["scores"]) for v in VARIANTS}}
                 for p in points]
    evaluated[0]["variant_scores"]["shared"]["D_plus_geometry"] = 0.
    return saved, {"grid_count": 2, "point_components": evaluated,
                   "selected": {"old": evaluated[1], "mixture": evaluated[1], "shared": evaluated[0]}}


def test_branch_preserves_independent_minima():
    saved, branch = branch_fixture()
    checked = validate_branch(saved, branch)
    assert checked["selected"]["shared"]["east_km"] == 0.
    assert checked["selected"]["mixture"]["east_km"] == 1.


@pytest.mark.parametrize("mutation", ["frequency", "coordinate", "selection", "duplicate", "nan"])
def test_branch_rejects_changed_evidence(mutation):
    saved, branch = branch_fixture()
    point = branch["point_components"][0]
    if mutation == "frequency": point["variant_scores"]["shared"]["D"] += .01
    elif mutation == "coordinate": point["latitude_deg"] += .01
    elif mutation == "selection": branch["selected"]["shared"] = branch["point_components"][1]
    elif mutation == "duplicate": branch["point_components"].append(point)
    else: point["variant_scores"]["shared"]["D_plus_geometry"] = float("nan")
    with pytest.raises(ValueError): validate_branch(saved, branch)
