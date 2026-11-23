"""Whole-region and phase-support guards for fine salvage."""

from collections import Counter
from hashlib import sha256
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from leo.analysis.localization_v3.region import SearchRegion
from leo.analysis.research.continuous_curve_fit import phase_frequency_from_states
from leo.analysis.research.orbit_phase_geometry import phase_shifted_states
from leo.analysis.research.retained_track_likelihood import PERIOD, profile
from leo.sky.frames import geodetic_to_ecef_km
from tools.pipeline_eval.variants import v5_tiled_salvage
from tools.pipeline_eval.variants.experimental import regional_envelope as trial


@pytest.mark.parametrize("latitude, longitude", [(0., 0.), (60., 170.), (-75., -145.)])
def test_observer_box_and_orbit_sensitivity(latitude, longitude):
    region = SearchRegion((latitude, longitude), 25.)
    anchor = region.latlon((-12.5, 5.2))
    observer = trial.ObserverDisk.from_region(region, anchor)
    radial = observer.center_km / np.linalg.norm(observer.center_km)
    position = np.array([observer.center_km + 500. * radial, observer.center_km + [1400, 1400, 1200]])
    velocity = np.array([[6.2, 1.2, -0.4], [3.1, -5.1, 3.4]])
    primary_f, primary_e = phase_frequency_from_states(position, velocity, *anchor)
    margin_f, margin_e = trial.projection_margins(
        position, velocity, observer, orbit_position_km=10., orbit_velocity_km_s=.02,
    )
    rng = np.random.default_rng(20261123)
    sites = [region.latlon(xy) for xy in rng.uniform(-12.5, 12.5, (128, 2))]
    sites += [region.latlon((e, n)) for e in (-12.5, 12.5) for n in (-12.5, 12.5)]
    for point in sites:
        assert np.linalg.norm(geodetic_to_ecef_km(*point, 0.) - observer.center_km) <= observer.position_radius_km
        direction = rng.normal(size=3)
        direction /= np.linalg.norm(direction)
        exact_f, exact_e = phase_frequency_from_states(
            position + 10. * direction, velocity + .02 * direction, *point,
        )
        assert np.all(np.abs(exact_f - primary_f) <= margin_f)
        assert np.all(np.abs(exact_e - primary_e) <= margin_e)


def sample_scan():
    times = np.arange(-17., 80.)
    position = np.zeros((1, len(times), 3))
    position[0, :, 0] = 6900.
    position[0, :, 1] = np.where(times < 35., times * 7., 245. + 8. * (times - 35.))
    velocity = np.zeros_like(position)
    velocity[0, :, 1] = 7. + .0001 * times**2
    return SimpleNamespace(sky=dict(time_s=times, position_km=position, velocity_km_s=velocity),
                           norads=[1], search_region=SearchRegion((0., 0.), 25.))


def test_phase_tiles_bound_every_interp_segment_and_rotation():
    scan = sample_scan()
    p_rate, v_rate = trial.phase_rates(scan.sky)
    times = np.array([20., 32., 50.])
    p0, v0 = phase_shifted_states(scan.sky, times, 0.0)
    for phase in np.linspace(-15., 15., 142):
        p, v = phase_shifted_states(scan.sky, times, phase)
        assert np.all(np.linalg.norm(p - p0, axis=-1) <= abs(phase) * p_rate[:, None])
        assert np.all(np.linalg.norm(v - v0, axis=-1) <= abs(phase) * v_rate[:, None])


def test_contrast_keeps_ties_and_unknowns_and_cancels_common_native_alias():
    f = np.array([[1., 5.], [4., 2.]])
    y = np.array([10., 20.])
    e = np.array([[0., -1.], [0., 0.]])
    margins = np.array([[2., 2.], [np.inf, np.inf]])
    alias_free = trial.phase_exclusions(f, e, margins, margins, y, [(0, 1)],
                                       np.ones(2), rf=1.)
    shifted = trial.phase_exclusions(f, e, margins, margins, y + 3 * PERIOD, [(0, 1)],
                                    np.ones(2), rf=1.)
    assert all(np.array_equal(before, after) for before, after in zip(alias_free, shifted, strict=True))
    assert not alias_free[0].any() and not alias_free[1].any()


@pytest.mark.parametrize("wrong_curve", [False, True])
def test_scope_matches_original_and_rejects_an_entire_support(wrong_curve):
    scan = sample_scan()
    coords = scan.search_region.center
    times = np.linspace(15., 50., 10)
    position, velocity = phase_shifted_states(scan.sky, times, 0.)
    f, _ = phase_frequency_from_states(position, velocity, *coords)
    y = f[0].copy()
    if wrong_curve:
        y[-1] += 100000.
    track = dict(times=times, values=y.copy())
    kernel = SimpleNamespace(
        selected_supports=lambda n: [(0, n)], raw_curvature=lambda t: True, profile=profile,
        paired_phase_frequency=trial.paired_phase_frequency,
        batch_noise_screen=lambda *_: {"noise_screen_pass": [True]},
    )
    args = (kernel, scan, track, y, np.full(len(times), 150.), 1., [0], coords)
    original = v5_tiled_salvage.fine_alternatives
    stock = original(*args)
    binding = sha256(Path(v5_tiled_salvage.__file__).read_bytes()).hexdigest()
    with trial.regional_fine_salvage(prune=True, expected_source_sha256=binding) as work:
        candidate = v5_tiled_salvage.fine_alternatives(*args)
    assert v5_tiled_salvage.fine_alternatives is original
    assert candidate == stock
    assert work["reject_trajectories"] == int(wrong_curve)
    assert work["profile_calls"] == 1 - int(wrong_curve)


def test_scope_falls_back_for_unbound_geometry():
    scan = sample_scan()
    times = np.linspace(15., 50., 10)
    observed = np.zeros(len(times))
    result = trial.regional_rejections(
        scan, 0, times, [(0, 10)], observed, np.ones(len(times)), 1., np.linspace(-15, 15, 121),
        scan.search_region.center, None,
    )
    assert result is None
    assert trial.ObserverDisk.from_region(scan.search_region, scan.search_region.latlon((13., 0.))) is None
    with pytest.raises(ValueError, match="salvage policy source"):
        with trial.regional_fine_salvage(prune=True, expected_source_sha256="bad"):
            pytest.fail("Unpinned code was accepted")


def test_unsupported_phase_support_keeps_edge():
    scan = sample_scan()
    scan.tracks = [dict(times=np.array([0., 35.]), values=np.array([0., 1e8]), rf_hz=11.5e9)]
    scan.rx_basis = [np.zeros((2, 1))]
    scan.curved = [0]
    settings = dict(phase_tile_s=5., orbit_position_km=10., orbit_velocity_km_s=.02)
    assert trial.contrast_census(scan, phase_limit_s=15., **settings)["reject_edges"] == 1
    assert trial.contrast_census(scan, phase_limit_s=30., **settings)["reject_edges"] == 0
