from importlib import import_module
from pathlib import Path

import pytest


trial = import_module("reports.ALGO08.single-core-2x.widened_face_sweep")


def sample():
    return {
        "case": "example",
        "original": {"center": [0., 0.], "width_km": 25.0},
        "reference_latlon": [0., -12.4 / 111.32],
        "expanded_fit": {"status": "ok", "arms": {
            "c0": {"latlon": [0., -13.0 / 111.32]},
            "fitted_c": {"latlon": [0., -12.0 / 111.32]},
        }},
        "decision": {"inside_original": {"c0": False, "fitted_c": True}, "publication": "withheld"},
    }


def test_closed_acceptance_intervals_cover_the_opposite_face_and_both_arms():
    row = trial.summarize_fit(sample())
    assert row["face"] == "west"
    assert row["inward_bias_km"] == pytest.approx({"c0": -.6, "fitted_c": .4, "paired": -.6})
    assert row["truth_clearance_keep_interval_km"]["paired"] == pytest.approx([.6, 24.6])
    for depth in (-1., -.1, .5, .7, 24.5, 24.7, 26.):
        west = -12.4 - depth
        for rule, window in row["truth_clearance_keep_interval_km"].items():
            points = {"c0": [-13.], "fitted_c": [-12.], "paired": [-13., -12.]}[rule]
            assert (window[0] <= depth <= window[1]) == all(west <= p <= west + 25 for p in points)


def test_band_has_an_open_omission_limit_and_strict_symmetric_separation():
    band = trial.error_band((-.75, .25), mirror_depth=.5)
    assert band["guaranteed_withhold_below_km"] == -.25
    assert band["guaranteed_keep_from_km"] == .75
    assert band["symmetric_depth_must_exceed_km"] == .5
    assert band["threshold_interval_lower_open_upper_closed_km"] == [-.25, -.25]
    assert not band["shared_threshold_exists"]
    assert trial.error_band((-.75, .25), mirror_depth=.5001)["shared_threshold_exists"]


def test_tangential_exclusion_violates_the_one_face_interpretation():
    row = sample()
    row["expanded_fit"]["arms"]["c0"]["latlon"][0] = 13 / 111
    with pytest.raises(ValueError, match="tangential limits"):
        trial.summarize_fit(row)


def test_all_archived_pairs_reproduce_original_membership():
    path = Path(trial.__file__).with_name("measurements") / "widened-offer-membership.json"
    scored = trial.sweep(path.read_bytes())
    assert [row["face"] for row in scored["fits"]] == ["north", "north", "west", "west"]
    assert not any(band["shared_threshold_exists"] for band in scored["observed_face_bands"].values())
