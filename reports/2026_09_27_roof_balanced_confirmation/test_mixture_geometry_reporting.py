from copy import deepcopy

import pytest

import mixture_geometry_reporting as report


def example():
    points = [{"east_km": float(i), "north_km": 0., "latitude_deg": 37.,
               "longitude_deg": -122. + i / 100.,
               "scores": {"D": float(i + 1), "D_plus_geometry": float(2 - i)}}
              for i in range(2)]
    saved = {"grid_count": 2, "point_components": points,
             "arms": {"D": {"selected": {**points[0], "tracks": []}},
                      "D_plus_geometry": {"selected": {**points[1], "tracks": []}}}}
    rows = [{**{k: v for k, v in point.items() if k != "scores"},
             "variant_scores": {name: dict(point["scores"]) for name in report.VARIANTS}}
            for point in points]
    rows[0]["variant_scores"]["mixture"]["D_plus_geometry"] = 0.
    return saved, {"grid_count": 2, "point_components": rows,
                   "selected": {"old": rows[1], "mean": rows[1], "mixture": rows[0]}}


def test_validates_all_calibrations_and_keeps_independent_minima():
    saved, branch = example()
    result = report.validate_branch(saved, branch)
    assert result["selected"]["D"]["east_km"] == 0.
    assert result["selected"]["mean"]["east_km"] == 1.
    assert result["selected"]["mixture"]["east_km"] == 0.


@pytest.mark.parametrize("mutation", ["mean_D", "mean_nan", "coordinate", "selection", "variant"])
def test_rejects_malformed_mean_or_mixture_evidence(mutation):
    saved, branch = example()
    if mutation == "mean_D": branch["point_components"][0]["variant_scores"]["mean"]["D"] += 1e-5
    elif mutation == "mean_nan": branch["point_components"][0]["variant_scores"]["mean"]["D_plus_geometry"] = float("nan")
    elif mutation == "coordinate": branch["point_components"][0]["latitude_deg"] += .01
    elif mutation == "selection": branch["selected"]["mixture"] = deepcopy(branch["point_components"][1])
    else: del branch["point_components"][0]["variant_scores"]["mean"]
    with pytest.raises(ValueError): report.validate_branch(saved, branch)


def test_reports_regressions_and_each_prior_separately():
    sessions = [f"s{i}" for i in range(4)]
    rows = [{"session_id": session, "prior": prior,
             "errors_km": {"D": 3., "old": 2., "mean": 1., "mixture": value}}
            for session in sessions
            for prior, value in (("sacramento", 2.), ("reno", .5))]
    summary = report.summarize(rows, sessions)
    assert summary["sacramento"]["mixture_vs"]["mean"]["worsened"] == 4
    assert summary["reno"]["mixture_vs"]["mean"]["improved"] == 4
    assert summary["combined"]["mean_error_km"]["mixture"] == 1.25


def test_summary_rejects_incomplete_duplicate_or_nonfinite_cohort():
    sessions = [f"s{i}" for i in range(4)]
    rows = [{"session_id": session, "prior": prior,
             "errors_km": {"D": 3., "old": 2., "mean": 1., "mixture": .5}}
            for session in sessions for prior in ("sacramento", "reno")]
    with pytest.raises(ValueError, match="complete cohort"):
        report.summarize(rows[:-1], sessions)
    with pytest.raises(ValueError, match="complete cohort"):
        report.summarize(rows[:-1] + [rows[0]], sessions)
    rows[0]["errors_km"]["mixture"] = float("nan")
    with pytest.raises(ValueError, match="nonfinite"):
        report.summarize(rows, sessions)
