import numpy as np

from leo.analysis.blind_regional_association import (
    BlindRegionalConfig,
    BlindRegionalTrack,
    solve_blind_regional_association,
)
from leo.analysis.research.regional_doppler import LIGHT_KM_S, REFERENCE_RF_HZ, Region, ScoreConfig


def _track(region, name, catalog_number, phase):
    n = 8
    point = region.points([0.0], [0.0]).ecef_km[0]
    time = np.arange(n, dtype=float)
    positions = np.empty((2, n, 3))
    velocities = np.empty_like(positions)
    for candidate in range(2):
        angle = phase + candidate * 0.8 + time * 0.001
        positions[candidate] = np.column_stack(
            (7000 * np.cos(angle), 7000 * np.sin(angle), np.full(n, 800 + 100 * candidate))
        )
        velocities[candidate] = np.column_stack(
            (-7 * np.sin(angle), 7 * np.cos(angle), np.zeros(n))
        )
    selected = 0
    delta = positions[selected] - point
    measured = (
        -REFERENCE_RF_HZ
        / LIGHT_KM_S
        * np.sum(delta * velocities[selected], axis=1)
        / np.linalg.norm(delta, axis=1)
        + 12_000
    )
    return BlindRegionalTrack(
        name,
        tuple(f"{name}-{i}" for i in range(n)),
        (2_000_000_000_000 + np.arange(n) * 1_000_000_000).astype(np.int64),
        measured,
        np.asarray([True, True, True, True, False, False, False, False]),
        np.asarray([catalog_number, catalog_number + 1]),
        positions,
        velocities,
        2,
        "sha256:" + "1" * 64,
        "sha256:" + ("2" if name == "a" else "3") * 64,
    )


def test_joint_search_is_blind_multimode_and_reopens_full_observations():
    region = Region(39.7392, -104.9903, 2000, 2000)
    tracks = (_track(region, "a", 100, 0.1), _track(region, "b", 200, 1.4))
    result = solve_blind_regional_association(
        tracks,
        region=region,
        config=BlindRegionalConfig(
            coarse_spacing_km=1000,
            coarse_track_limit=1,
            search_observation_limit=4,
            alternative_mode_limit=2,
            refinement_mode_limit=1,
            refinement_grid_side=5,
            refinement_half_width_km=(500,),
            mode_separation_km=500,
            score=ScoreConfig(minimum_elevation_deg=-90),
        ),
    )

    assert result.state == "diagnostic"
    assert result.blind_positioning and not result.site_conditioned
    assert result.selected_track_count == 2 and result.coarse_track_count == 1
    assert result.omitted_coarse_track_count == 1
    assert result.full_observation_count == 16
    assert result.search_observation_count == 8
    assert result.omitted_search_observation_count == 8
    assert result.refined_mode_count == 1 and len(result.modes) == 2
    assert tuple(
        item.top_candidates[0].catalog_number for item in result.modes[0].track_associations
    ) == (100, 200)
    assert all(
        len(item.time_s) == len(item.measured_hz) == len(item.prediction_hz) == 8
        for item in result.modes[0].track_associations
    )


def test_heldout_values_do_not_change_training_selected_mode():
    region = Region(39.7392, -104.9903, 2000, 2000)
    track = _track(region, "a", 100, 0.1)
    poisoned = BlindRegionalTrack(
        **{
            **{field: getattr(track, field) for field in track.__dataclass_fields__},
            "measured_hz": np.where(track.training, track.measured_hz, track.measured_hz + 1e6),
        }
    )
    config = BlindRegionalConfig(
        coarse_spacing_km=1000,
        alternative_mode_limit=1,
        refinement_mode_limit=1,
        refinement_grid_side=5,
        refinement_half_width_km=(500,),
        score=ScoreConfig(minimum_elevation_deg=-90),
    )
    first = solve_blind_regional_association((track,), region=region, config=config)
    second = solve_blind_regional_association((poisoned,), region=region, config=config)
    assert (first.modes[0].east_km, first.modes[0].north_km) == (
        second.modes[0].east_km,
        second.modes[0].north_km,
    )
    assert (
        first.modes[0].track_associations[0].top_candidates[0].catalog_number
        == second.modes[0].track_associations[0].top_candidates[0].catalog_number
    )
    assert first.modes[0].heldout_log_evidence != second.modes[0].heldout_log_evidence


def test_invalid_track_arrays_and_all_invisible_catalogue_are_explicit():
    region = Region(39.7392, -104.9903, 2000, 2000)
    track = _track(region, "a", 100, 0.1)
    invalid = BlindRegionalTrack(
        **{
            **{field: getattr(track, field) for field in track.__dataclass_fields__},
            "utc_ns": track.utc_ns[::-1],
        }
    )
    with np.testing.assert_raises_regex(ValueError, "observation arrays"):
        solve_blind_regional_association((invalid,), region=region)

    result = solve_blind_regional_association(
        (track,),
        region=region,
        config=BlindRegionalConfig(
            coarse_spacing_km=1000,
            alternative_mode_limit=1,
            refinement_mode_limit=1,
            refinement_grid_side=5,
            refinement_half_width_km=(500,),
            score=ScoreConfig(minimum_elevation_deg=90),
        ),
    )
    association = result.modes[0].track_associations[0]
    assert association.association_state == "unassigned"
    assert association.top_candidates == () and association.null_weight == 1.0
    assert association.prediction_hz == association.measured_hz == ()
