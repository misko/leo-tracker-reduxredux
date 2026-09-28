import copy

import pytest

import run_mixture_geometry_replay as runner


def branch():
    scores = {"D": 1., "D_plus_detection": 2., "D_plus_geometry": 3.,
              "D_plus_reversed_geometry": 4.}
    return {"grid_count": 2, "point_components": [
        {"east_km": 0., "north_km": 0., "latitude_deg": 1., "longitude_deg": 2.,
         "scores": scores},
        {"east_km": 1., "north_km": 0., "latitude_deg": 1.1, "longitude_deg": 2.1,
         "scores": scores | {"D_plus_geometry": 2.}},
    ]}


def replay_rows():
    rows = []
    for row in branch()["point_components"]:
        rows.append({"east_km": row["east_km"], "north_km": row["north_km"],
                     "latitude_deg": row["latitude_deg"],
                     "longitude_deg": row["longitude_deg"],
                     "variant_scores": {name: dict(row["scores"])
                                        for name in runner.VARIANTS}})
    return rows


def test_parity_checks_every_point_and_all_variant_D():
    report = runner.parity_report(branch(), replay_rows())
    assert report["passed"] and report["points"] == 2
    bad = replay_rows(); bad[1]["variant_scores"]["old"]["D_plus_geometry"] += 2e-7
    with pytest.raises(ValueError, match="old local-grid parity"):
        runner.parity_report(branch(), bad)
    bad = replay_rows(); bad[0]["variant_scores"]["mixture"]["D"] += 2e-12
    with pytest.raises(ValueError, match="changed D"):
        runner.parity_report(branch(), bad)


def test_parity_rejects_inventory_and_variant_changes():
    bad = replay_rows()[:-1]
    with pytest.raises(ValueError, match="coordinate inventory"):
        runner.parity_report(branch(), bad)
    bad = replay_rows(); del bad[0]["variant_scores"]["mean"]
    with pytest.raises(ValueError, match="variant or arm"):
        runner.parity_report(branch(), bad)
    bad = replay_rows(); bad[0]["latitude_deg"] += 1e-6
    with pytest.raises(ValueError, match="geographic coordinate"):
        runner.parity_report(branch(), bad)


def test_selection_is_deterministic_score_east_north():
    rows = replay_rows()
    assert runner.select_min(rows, "mixture")["east_km"] == 1.
    tied = copy.deepcopy(rows)
    tied[0]["variant_scores"]["mixture"]["D_plus_geometry"] = 2.
    assert runner.select_min(tied, "mixture")["east_km"] == 0.
