import hashlib

import numpy as np
import pytest

from leo.analysis.localization_v3.families import AnchoredFamilies
from leo.analysis.localization_v3.hierarchical import hierarchical_bound
from leo.analysis.localization_v3.marginal import integrated_gaussian
from leo.analysis.localization_v3.orbit_modes import previous_bank
from leo.analysis.localization_v3.position import NormalPosition, fit, refreshed
from leo.analysis.localization_v3.region import SearchRegion
from tests.analysis.test_localization_v3_scan import example
from tests.operations.test_causal_tle_catalogue import at_day


def prepared():
    scan, _, _, state, _ = example()
    scan.search_region = SearchRegion((0., 0.))
    # No matching prior object: this checks the declared unavailable-history path.
    scan.norads = scan.sky['norad'] = np.array([99999])
    scan.previous_tle = at_day(232)
    scan.previous_tle_sha256 = hashlib.sha256(scan.previous_tle.encode()).hexdigest()
    for i, track in enumerate(scan.tracks):
        track['observation_ids'] = [f'{i}-{k}' for k in range(len(track['times']))]
    scan.fixed_window_noise.update(extra_parameter_BIC_gain=0,
        per_observation_noise_sigma_hz={oid:150. for t in scan.tracks
                                        for oid in t['observation_ids']})
    # Only one RX/channel owns the family, so no orbital correction is supported.
    rows = [dict(component='curved', active_curvature=True, candidate_index=0,
                 candidate_norad=99999)]
    seed = dict(rows=rows, state=state)
    anchor = AnchoredFamilies(scan, seed, 'receiver_smooth', False, [0., 0.])
    return scan, dict(seed=seed, aliases=anchor.alias)


def test_regional_coordinate_origin_is_explicit_and_not_the_screening_origin():
    scan, _, _, _, _ = example()
    region = SearchRegion((10., 20.))
    assert region.latlon([0., 0.]) == (10., 20.)
    native = region.native_point(scan, [0., 0.])
    assert scan.latlon(native) == pytest.approx((10., 20.), abs=1e-13)
    assert len(region.grid) == 25
    assert region.grid[0] == (-12.5, -12.5)
    with pytest.raises(ValueError, match='regional'):
        SearchRegion((90., 0.))


def test_previous_elements_binding_checked_even_after_cache_fill():
    scan, _ = prepared()
    bank, available, phase = previous_bank(scan, [0])
    assert not available and not phase
    np.testing.assert_array_equal(bank['position_km'], scan.sky['position_km'])
    scan.previous_tle += '\n'
    with pytest.raises(ValueError, match='bytes differ'):
        previous_bank(scan, [0])


def test_c_arms_share_observations_and_priors_with_only_one_additional_column():
    scan, node = prepared()
    a = NormalPosition(scan, node, 150., False)
    b = NormalPosition(scan, node, 150., True)
    assert a.members == b.members and a.alias == b.alias
    np.testing.assert_array_equal(a.values, b.values)
    np.testing.assert_array_equal(a.phase_sigma, b.phase_sigma)
    np.testing.assert_array_equal(a.point_noise, b.point_noise)
    np.testing.assert_array_equal(a.hardware, b.hardware[:, :-1])
    assert a.hardware.shape[1] == 8 and b.hardware.shape[1] == 9
    assert not a.supported and not b.supported


def test_masks_retain_nuisance_support_and_full_residual_diagnostics():
    scan, node = prepared()
    full = NormalPosition(scan, node, 150., False)
    keep = np.ones(len(full.values), bool)
    keep[::3] = False
    masked = NormalPosition(scan, node, 150., False, keep=keep)
    assert masked.members == full.members and masked.labels == full.labels
    result = masked.calculate(np.zeros(2))
    assert result['conditional_residual_hz'].shape == full.values.shape
    assert np.isfinite(result['residual']).all()
    with pytest.raises(ValueError, match='nonempty'):
        NormalPosition(scan, node, 150., False, keep=np.zeros(len(full.values), bool))


def test_joint_gaussian_matches_dense_covariance():
    rng = np.random.default_rng(126)
    y, u, s = rng.normal(size=8), rng.normal(size=(8, 3)), np.linspace(1., 2., 8)
    result = integrated_gaussian(y, u, s)
    covariance = np.diag(s*s) + u @ u.T
    expected = y @ np.linalg.solve(covariance, y)
    assert result['quadratic'] == pytest.approx(expected, abs=1e-12)
    assert result['logvolume'] == pytest.approx(
        np.linalg.slogdet(covariance)[1]-np.sum(np.log(s*s)), abs=1e-12)


def test_group_noise_downweights_a_noisy_fragment_without_dropping_points():
    rng = np.random.default_rng(127)
    y = np.r_[rng.normal(size=30), 30*rng.normal(size=30)]
    result = hierarchical_bound(y, np.ones((60, 1)), 1., np.repeat([0, 1], 30))
    assert result['noise_precision'][1] < result['noise_precision'][0] / 10
    assert result['conditional_residual_hz'].shape == y.shape
    assert result['effective_observations'] == 60


def test_position_fit_is_bounded_and_reports_active_points():
    scan, node = prepared()
    problem = NormalPosition(scan, node, 150., False)
    result = fit(problem, iterations=2)
    assert np.all(abs(result['parameters']) <= 12.5)
    assert result['active_points'] == len(problem.values)
    assert np.isfinite(result['residual_rms_hz'])


def test_phase_refresh_relinearizes_without_replacing_the_absolute_phase_prior():
    scan, node = prepared()
    problem, result, history = refreshed(scan, 150., node, 'c0', rounds=2, iterations=1)
    assert len(history) == 2 and result is history[-1]['fit']
    np.testing.assert_array_equal(history[0]['phase_reference'], np.zeros(len(problem.labels)))
    np.testing.assert_array_equal(problem.reference,
        np.clip(history[0]['posterior_phase_s'], -15., 15.))
    np.testing.assert_array_equal(problem.phase_sigma, np.ones(len(problem.labels)))
    np.testing.assert_array_equal(node['seed']['state']['phases'], np.zeros(len(scan.norads)))
