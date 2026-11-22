from collections import Counter
from types import SimpleNamespace

import numpy as np
import pytest

from leo.analysis.localization_v3.region import SearchRegion
from leo.analysis.research.retained_track_likelihood import NOISE, PERIOD
from leo.sky.frames import ecef_to_enu_matrix, geodetic_to_ecef_km
from tools.pipeline_eval.variants.experimental import regional_reassignment as study
from tools.pipeline_eval.variants.experimental.regional_reassignment import (
    contrast_log_ratio, possible_horizon, probes, score_track,
)


def test_probe_sets_have_equal_counts_and_four_face_symmetry():
    region = SearchRegion((-52, 144), 25)
    rows = list(probes(region))
    assert Counter(p["side"] for p in rows) == dict(inside=48, exterior=48)
    assert len({tuple(p["xy_km"]) for p in rows}) == len(rows)
    geometry = {(p["side"], *p["xy_km"]) for p in rows}
    for side, x, y in geometry:
        assert (max(abs(x), abs(y)) <= region.half_width_km) == (side == "inside")
        assert (side, -y, x) in geometry


def test_centered_phase_integral_matches_dense_contrast_covariance():
    y = np.array([110, 40, 300, 92])
    f = np.array([[60, 89, 400, 20], [10, 80, 200, 230]])
    h = np.array([[115, 45, 33, 89], [58, 980, 110, 223]])
    expected = []
    for prediction, phase in zip(f, h, strict=True):
        signal, slope = y - prediction, phase[1:] - phase[0]
        contrast = signal[1:] - signal[0]
        cov = NOISE**2 * (np.eye(len(slope)) + 1) + np.outer(slope, slope)
        expected.append(len(slope) * np.log(PERIOD) - .5 * (
            contrast @ np.linalg.solve(cov, contrast) + np.linalg.slogdet(cov)[1]
            + len(slope) * np.log(2 * np.pi)))
    np.testing.assert_allclose(contrast_log_ratio(y, f, h), expected)
    np.testing.assert_allclose(contrast_log_ratio(y + 739, f - 950, h + 3200), expected)


def test_common_outlier_and_catalogue_include_invisible_orbits():
    y = np.array([0, 47, 30, 80])
    f = np.array([y, y + np.arange(len(y)) * 1000])
    h = np.zeros_like(f)
    elevation = np.ones_like(f)
    elevation[1, 0] = -1
    ratios = contrast_log_ratio(y, f[:1], h[:1])
    evidence, owner = score_track(y, f, elevation, h, np.array([64, 65]), 101)
    assert owner == 64
    assert evidence == pytest.approx(np.logaddexp(0, ratios[0] - np.log(101)))
    assert score_track(y, f, -np.ones_like(f), h, np.array([64, 65]), 101) == (0., None)


def test_common_horizon_bound_cannot_exclude_an_explicitly_visible_orbit():
    region = SearchRegion((63, 57), 60)
    locations = [row["latlon"] for row in probes(region)]
    rng = np.random.default_rng(8)
    p = geodetic_to_ecef_km(*region.center, 0) + rng.normal(0, 400, (6, 10, 3))
    visible = np.zeros((6, 10), bool)
    for loc in locations:
        visible |= (p - geodetic_to_ecef_km(*loc, 0)) @ ecef_to_enu_matrix(*loc)[2] >= 0
    assert np.all(possible_horizon(p, region.center, locations)[visible])
    assert not np.all(possible_horizon(p, region.center, locations))


def test_all_native_observations_stay_in_the_denominator_when_owners_change(monkeypatch):
    region = SearchRegion((12, 14), 25)
    y = np.array([0, 100, 300], float)
    offset = np.array([0, 500, 1600], float)
    labels = np.array([1, 2])
    observations = [dict(observation_id=i, receiver=1 + (i >= 4)) for i in range(8)]
    tracks = [dict(key=str(r), receiver=r, observation_ids=ids, rf_hz=11.5e9,
                   times=np.asarray(ids, float), values=y)
              for r, ids in ((1, [0, 1, 2]), (2, [4, 5, 6]))]
    prepared = dict(observations=observations, tracks=tracks, metadata=dict(anchor_utc_ns=0))
    monkeypatch.setattr(study, "orbit_geometry", lambda *args: (object(), labels))

    def projection(geometry, lat, lon):
        first = np.r_[y, y + offset]
        second = np.r_[y + offset, y]
        if lon > region.center[1]:
            first, second = second, first
        return np.asarray([first, second]), np.ones((2, 6)), np.zeros((2, 6))

    monkeypatch.setattr(study, "phase_linear_frequency", projection)
    result = study.evaluate(prepared, SimpleNamespace(satellite_numbers=labels), region)
    assert (result["original_points"], result["graph_points"]) == (8, 6)
    assert result["receiver_points"] == {1: 4, 2: 4}
    positive, negative = result["points"][:6:3]
    assert positive["owners"] == {"1": 2, "2": 1}
    assert negative["owners"] == {"1": 1, "2": 2}
    ratio, _ = score_track(y, np.array([y, y + offset]), np.ones((2, 3)),
                           np.zeros((2, 3)), labels, len(labels))
    assert positive["score"] == pytest.approx(2 * ratio / 8)
    assert negative["receiver_scores"] == pytest.approx({"1": ratio / 4, "2": ratio / 4})


def test_only_a_strictly_positive_pooled_gain_would_withhold():
    inside = dict(side="inside", xy_km=[1, 0], score=2., receiver_scores={"1": 1., "2": 3.})
    outside = dict(side="exterior", xy_km=[5, 0], score=2., receiver_scores={"1": 2., "2": 2.})
    tied = study.summarize([inside, outside])
    assert not tied["would_withhold"]
    assert tied["receivers"]["1"]["gain"] > 0 and tied["receivers"]["2"]["gain"] < 0
    assert study.summarize([inside, dict(outside, score=3.)])["would_withhold"]
    assert not study.summarize([inside, dict(outside, score=1.)])["would_withhold"]
