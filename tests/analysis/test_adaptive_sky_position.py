"""Wide prior geometry and randomized partition provenance for the sky study."""

import importlib.util
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from leo.analysis.research.regional_doppler import Region, centered_errors


def replay_module():
    path = Path(__file__).resolve().parents[2] / "tools/replay_regional_doppler.py"
    spec = importlib.util.spec_from_file_location("regional_replay_test", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_denver_9000_mile_prior_has_finite_spherical_coordinates():
    region = Region(39.7392, -104.9903, 9000 * 1.609344, 9000 * 1.609344)
    grid = region.grid(500)
    assert len(grid) == 29**2
    assert np.all(np.isfinite(grid.ecef_km))
    assert np.all(np.abs(grid.latitude_deg) <= 90)
    lat, lon = region.coordinates(0, 0)
    np.testing.assert_allclose([lat, lon], [39.7392, -104.9903])


def test_random_partition_is_repeatable_response_free_and_used_without_time_cut():
    replay = replay_module()
    t = np.arange(30.0)
    doc = {
        "inventory": {"partition": "randomized"},
        "series": [
            dict(
                tracklet_id="arc",
                channel=1,
                t_s=t.tolist(),
                y_hz=(10 * t + 100).tolist(),
                candidate_ids=[str(i) for i in range(30)],
                actual_rf_hz=11.2e9,
            )
        ],
        "episodes": [dict(episode_id="arc", members=["arc"])],
    }
    a = replay.load_observations(doc, max_per_partition=0)[0][1]
    assert a.partition == "randomized"
    assert max(a.time_s[a.training]) > min(a.time_s[~a.training])
    np.testing.assert_allclose(centered_errors(a, 10 * a.time_s), [0, 0], atol=1e-9)
    doc["series"][0]["y_hz"] = [1e8] * 30
    b = replay.load_observations(doc, max_per_partition=0)[0][1]
    np.testing.assert_array_equal(a.training, b.training)
    np.testing.assert_array_equal(a.time_s, b.time_s)


def test_site_selected_ids_cannot_enter_a_blind_inventory():
    replay = replay_module()
    catalogue = SimpleNamespace(satellite_numbers=[111, 222, 333])
    metadata = {"fixed_candidates": {"arc": 222}}
    with pytest.raises(ValueError, match="conditional identity provenance"):
        replay.episode_catalogue_indices(metadata, catalogue, [0, 1, 2], "arc", conditional=False)
    assert replay.episode_catalogue_indices(
        metadata, catalogue, [0, 1, 2], "arc", conditional=True
    ) == [1]
    assert replay.episode_catalogue_indices({}, catalogue, [0, 1, 2], "arc", conditional=False) == [
        0,
        1,
        2,
    ]
