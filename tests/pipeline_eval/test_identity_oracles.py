import numpy as np
import pytest

from tools.pipeline_eval.qualification import fresh_scenes as fresh
from tools.pipeline_eval.qualification import identity_oracles as oracle
from tools.pipeline_eval.qualification import identity_sweep as sweep
from tools.pipeline_eval.scoring import distance_km


def test_held_frame_values_cannot_choose_the_identity():
    times = np.arange(12, dtype=float)
    period = 13333.333333
    tracks, choices = [], []
    for rx in (0, 1):
        tracks.append(oracle.Track(rx, 1, 11.325e9, times, times, times, 12))
        cfo = np.full((2, 12), 1500.0)
        epoch = np.stack((3 * times + 500, times**2 + 300))
        choices.append(oracle.Candidates(np.array([44, 31]), cfo, epoch, np.array([0.0, 0.0])))
    result = oracle.identify(tracks, choices, period, "joint", False)
    for item in choices:
        item.epoch[0, oracle.HELD] += 3000.0
        item.epoch[1, oracle.HELD] = 0.0
    changed = oracle.identify(tracks, choices, period, "joint", False)
    assert [r["selected_norad"] for r in result["rows"]] == [44, 44]
    assert [r["selected_norad"] for r in changed["rows"]] == [44, 44]
    assert changed["rows"][0]["held_epoch_rms_samples"] > 2500


def test_frame_center_profiles_across_the_wrap_boundary():
    assert abs(abs(oracle._center(np.array([998.0, 2.0]), 1000))) < 1e-8
    slope = oracle._frame_clock(np.array([[995.0, 998.0, 1.0, 4.0]]), np.arange(4)[None], 1000)
    assert slope == pytest.approx(3)


def test_fresh_offers_are_paired_and_public_fields_omit_labels():
    cases = ["a", "b", "c", "d", "e"]
    sites = [[34, 120], [-56, -177], [12, 2], [23, -45], None]
    truth = {case: {"latlon": site} for case, site in zip(cases, sites, strict=True)}
    queries, labels = fresh._offers(cases, truth, np.random.default_rng(9997))
    assert len(queries) == len(labels) == 9
    assert len({q["id"] for q in queries}) == 9
    for q in queries:
        assert set(q) == {"id", "capture_id", "tile"}
        assert q["tile"]["width_km"] == 25.0
        label = labels[q["id"]]
        error = distance_km(label["latlon"], q["tile"]["center"])
        if label["condition"] == "present":
            assert 8 < error < 10
        elif label["condition"] == "missing":
            assert 45 < error < 115
        else:
            assert error is None
    for case in cases[:-1]:
        conditions = {labels[q["id"]]["condition"] for q in queries if q["capture_id"] == case}
        assert conditions == {"present", "missing"}


def test_displacement_score_distinguishes_visibility_shortlist_and_choice():
    trials = [
        {
            "visibility": [[4, 3], [8, 12], [7, 14]],
            "shortlist": [[3], [8], [14]],
            "nominations": {"shape": {"c0": [3, 8, 14]}},
        }
    ]
    (result,) = list(sweep._score(trials, [4, 8, 21]))
    assert result["true_visible"] == 2
    assert result["true_shortlisted"] == 1
    assert result["methods"]["shape"]["c0"]["correct_tracklets"] == 1
