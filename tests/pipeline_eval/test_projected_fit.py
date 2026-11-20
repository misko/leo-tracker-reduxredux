import json
from datetime import UTC, datetime

import numpy as np
import pytest
from sgp4.api import SatrecArray

from leo.sky.frames import (
    ecef_to_enu_matrix,
    geodetic_to_ecef_km,
    greenwich_mean_sidereal_time_rad,
    julian_day_from_utc_ns,
    teme_to_ecef,
)
from leo.sky.propagation import element_line_checksum, parse_element_sets
from tools.pipeline_eval.variants.projected_fit import run

ANCHOR = int(datetime(2026, 1, 5, tzinfo=UTC).timestamp()) * 10**9
SITE = (38.047, -122.026)
OFFER = {"id": "site", "center": [38.0, -122.07]}
OTHER_OFFER = {"id": "decoy", "center": [38.48, -121.88]}


def _tle(number, node, argument, inclination, movement, epoch=4.5):
    first = f"1 {number:05d}U 26001A   26{epoch:012.8f}  .00000000  00000-0  00000-0 0  999"
    second = (
        f"2 {number:05d} {inclination:8.4f} {node:8.4f} 0005000"
        f"   0.0000 {argument:8.4f} {movement:11.8f}    1"
    )
    return "".join(f"{line}{element_line_checksum(line)}\n" for line in (first, second))


@pytest.fixture(scope="module")
def scene():
    rng = np.random.default_rng(452679)
    catalog_text = "".join(
        _tle(
            i, rng.uniform(0, 360), rng.uniform(0, 360), rng.uniform(45, 92), rng.uniform(15, 15.5)
        )
        for i in range(7100, 9100)
    )
    catalog = parse_element_sets(catalog_text)
    site = geodetic_to_ecef_km(*SITE, 0.0)
    up = ecef_to_enu_matrix(*SITE)[2]
    tracks = []
    selected = set()
    for start in (5.1, 242.4, 492.8, 693.7):
        times = start + np.linspace(0.0, 90.0, 33)
        jd, fraction = julian_day_from_utc_ns(ANCHOR + np.rint(times * 1e9).astype("int64"))
        errors, positions, velocities = SatrecArray(catalog.satellites).sgp4(jd, fraction)
        assert not errors.any()
        positions, velocities = teme_to_ecef(
            positions,
            velocities,
            greenwich_mean_sidereal_time_rad(jd, fraction),
        )
        ray = positions - site
        ray /= np.linalg.norm(ray, axis=-1, keepdims=True)
        elevation = ray @ up
        eligible = np.flatnonzero((elevation > 0.25).all(axis=1))
        ranked = sorted(eligible, key=lambda index: (-elevation[index].max(), index))
        for index in [i for i in ranked if i not in selected][:16]:
            selected.add(index)
            rf = rng.uniform(10.7e9, 12.4e9)
            doppler = -rf / 299_792.458 * np.einsum("ti,ti->t", ray[index], velocities[index])
            values = doppler + rng.normal(0.0, 15.0, len(times)) + rng.uniform(-50e3, 50e3)
            tracks.append(dict(times=times.tolist(), values=values.tolist(), rf_hz=rf))
    assert len(tracks) >= 12
    return dict(
        anchor_utc_ns=ANCHOR,
        cutoff_utc_ns=ANCHOR - 10**9,
        catalog_timestamp_ns=ANCHOR - 3600 * 10**9,
        duration_s=800.0,
        tracks=tracks,
    ), catalog_text


def _case(tmp_path, observation, catalog_text, *offers):
    observation_path, catalog_path = tmp_path / "observation.json", tmp_path / "causal.tle"
    observation_path.write_text(json.dumps(observation))
    catalog_path.write_text(catalog_text)
    return dict(observation_path=observation_path, catalog_path=catalog_path, regions=list(offers))


def test_anonymous_fit_and_rf_calibration_invariance(scene, tmp_path):
    observation, catalog = scene
    case = _case(tmp_path, observation, catalog, OTHER_OFFER, OFFER)
    solution = run(case, tmp_path)
    assert solution["status"] == "ok", solution
    arm = solution["arms"]["c0"]
    assert arm["region_id"] == OFFER["id"]
    assert (
        np.linalg.norm(geodetic_to_ecef_km(*arm["latlon"], 0.0) - geodetic_to_ecef_km(*SITE, 0.0))
        < 0.6
    )
    assert 0.0 < arm["rf_rms_hz"] < 30.0
    assert solution["arms"]["fitted_c"] == arm

    tracks = []
    for i, track in enumerate(observation["tracks"]):
        offset = 37_000.0 * (track["rf_hz"] / 1e9 - 11.5) + (i % 5 - 2) * 2_500_000 / 11
        tracks.append(dict(track, values=[value + offset for value in track["values"]]))
    shifted = _case(tmp_path, dict(observation, tracks=tracks[::-1]), catalog, OFFER, OTHER_OFFER)
    repeated = run(shifted, tmp_path)
    assert repeated["status"] == "ok", repeated
    other = repeated["arms"]["c0"]
    assert other["region_id"] == arm["region_id"]
    assert other["latlon"] == pytest.approx(arm["latlon"], abs=1e-9)
    assert other["rf_rms_hz"] == pytest.approx(arm["rf_rms_hz"], abs=1e-7)


def test_wrong_offer_withholds_diagnostic_coordinate(scene, tmp_path):
    observation, catalog = scene
    case = _case(tmp_path, observation, catalog, OTHER_OFFER)
    result = run(case, tmp_path)
    assert result["status"] == "withheld", result
    for arm in result["arms"].values():
        assert arm["latlon"] is None
        assert arm.get("region_id") is None
        assert len(arm["forced_latlon"]) == 2


def test_missing_and_future_only_orbits(scene, tmp_path):
    observation, _ = scene
    future_tle = _tle(7100, 30, 160, 60, 15.2, epoch=5.01)
    case = _case(tmp_path, observation, future_tle, OFFER)
    result = run(case, tmp_path)
    assert result["status"] == "withheld"
    assert result["metrics"]["propagated_states"] == 0
    assert result["arms"]["c0"]["latlon"] is None

    case = _case(
        tmp_path, dict(observation, catalog_timestamp_ns=ANCHOR + 10**9), future_tle, OFFER
    )
    assert run(case, tmp_path)["status"] == "unavailable"
    assert run(dict(case, catalog_path=None), tmp_path)["status"] == "unavailable"


def test_insufficient_tracks_withhold(scene, tmp_path):
    observation, catalog = scene
    case = _case(tmp_path, dict(observation, tracks=observation["tracks"][:5]), catalog, OFFER)
    result = run(case, tmp_path)
    assert result["status"] == "withheld"
    assert result["metrics"]["tracks"] == 5
    assert result["arms"]["c0"]["latlon"] is None
