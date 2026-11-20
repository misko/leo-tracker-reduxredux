import json

import numpy as np
import pytest

from leo.sky.frames import ecef_to_enu_matrix, geodetic_to_ecef_km
from leo.sky.propagation import parse_element_sets
from tests.pipeline_eval import geometry
from tools.pipeline_eval.variants.orbit_interp import run


@pytest.fixture(scope="module")
def case(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("orbit_interp")
    catalog_path, observation_path = tmp / "causal.tle", tmp / "observation.json"
    rng = np.random.default_rng(550)
    catalog = "".join(
        geometry.tle(
            number,
            4.45,
            rng.uniform(0, 360),
            rng.uniform(0, 360),
            rng.uniform(75, 100),
            rng.uniform(14.8, 15.8),
        )
        for number in range(1000, 1448)
    )
    catalog_path.write_text(catalog)
    satellites = parse_element_sets(catalog)
    truth = (80.02, -179.86)
    site = geodetic_to_ecef_km(*truth, 0.0)
    up = ecef_to_enu_matrix(*truth)[2]
    tracks = []
    seen = set()
    for start in (6.3, 21.4, 133.2, 164.7):
        times = np.linspace(start, start + 55.1, 18)
        position, velocity = geometry.direct_states(satellites, times)
        delta = position - site
        ray = delta / np.linalg.norm(delta, axis=-1)[..., None]
        visible = np.flatnonzero(((ray @ up) > 0.26).all(axis=1))
        for index in [i for i in visible if i not in seen][:6]:
            seen.add(index)
            rf = rng.uniform(10.7e9, 12.4e9)
            doppler = -(rf / 299792.458) * np.sum(ray[index] * velocity[index], axis=1)
            offset = 28_000.0 * (rf / 1e9 - 11.5)
            tracks.append(
                dict(
                    times=times.tolist(),
                    values=(doppler + offset).tolist(),
                    rf_hz=rf,
                    receiver=1,
                    channel=len(tracks),
                )
            )
    observation = dict(vars(geometry.observation()), tracks=tracks)
    observation_path.write_text(json.dumps(observation))
    return dict(
        id="generated-dateline",
        observation_path=observation_path,
        catalog_path=catalog_path,
        regions=[
            dict(id="date-line", center=[79.94, 179.95]),
            dict(id="neighbor", center=[79.54, 179.95]),
        ],
    )


def test_reused_orbits_drive_complete_receiver_with_equal_evidence(case, tmp_path):
    result = run(case, tmp_path)
    metrics = result["metrics"]

    assert result["status"] == "ok"
    assert result["arms"]["c0"] == result["arms"]["fitted_c"]
    assert result["arms"]["c0"]["latlon"] == metrics["control_latlon"]
    assert result["arms"]["c0"]["latlon"] == pytest.approx([80.02, -179.86], abs=0.025)
    assert metrics["null_schedules"] == 19
    assert metrics["same_work"] and metrics["same_decision"] and metrics["same_shape_evidence"]
    assert 0 < metrics["candidate_sgp4_evaluations"] < metrics["control_sgp4_evaluations"]
    assert metrics["projection_tables_aligned"] and metrics["projection_rows"] > 0
    assert metrics["tile_center_12ghz_doppler_max_error_hz"] == 0.0
    assert metrics["position_max_error_km"] == 0.0
    assert metrics["velocity_max_error_km_s"] == 0.0
    assert metrics["acceleration_max_error_km_s2"] == 0.0
    json.dumps(result, allow_nan=False)


def test_far_offers_withhold_coordinates_and_missing_catalog_is_unavailable(case, tmp_path):
    absent = dict(
        case,
        regions=[
            dict(id="far", center=[-74.0, 60.0]),
            dict(id="neighbor", center=[-74.3, 60.0]),
        ],
    )
    result = run(absent, tmp_path)
    assert result["status"] == "withheld"
    assert all(arm["latlon"] is None for arm in result["arms"].values())
    assert result["metrics"]["same_decision"]
    assert result["metrics"]["same_forced_position"]

    missing = run(dict(case, catalog_path=None), tmp_path)
    assert missing["status"] == "unavailable"
    assert "arms" not in missing
