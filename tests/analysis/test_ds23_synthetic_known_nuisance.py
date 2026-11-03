from pathlib import Path
import sys
import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'tools'))
from ds23_synthetic_known_nuisance import conditional_prior, generating_linear_bias, COMPONENTS


@pytest.fixture
def truth():
    widths = (8, 6, 2, 3, 4)
    return dict(coordinate_widths=widths, selected_coefficients=np.arange(sum(widths), dtype=float),
        true_phases_s=[2., -3.], latent_seed=219)


def test_empty_oracle_recovers_original_prior(truth):
    mean, scales, groups = conditional_prior(truth['coordinate_widths'], False,
        [1., -1.], [2., 3.], truth, [])
    np.testing.assert_array_equal(mean[14:16], [.5, -1/3])
    np.testing.assert_array_equal(np.delete(mean, [14, 15]), 0.)
    np.testing.assert_array_equal(scales[-4:], .3)
    np.testing.assert_array_equal(scales[:-4], 1.)
    np.testing.assert_array_equal(groups[14:16], [0, 1])


def test_known_fitted_c_maps_truth_with_no_coordinate_shift_leak(truth):
    mean, scale, groups = conditional_prior(truth['coordinate_widths'], True,
        [1., -1.], [2., 3.], truth, COMPONENTS)
    expected = np.insert(truth['selected_coefficients'], 8, 0.)
    expected[15:17] = [1., -1.]
    np.testing.assert_array_equal(mean, expected)
    np.testing.assert_allclose(scale[:-4], 1e-5)
    np.testing.assert_allclose(scale[-4:], .3e-5)
    assert np.all(groups == -1)


def test_only_known_phase_changes_phase_prior(truth):
    mean, scales, groups = conditional_prior(truth['coordinate_widths'], False,
        [1., -1.], [2., 3.], truth, ['phase'])
    np.testing.assert_array_equal(mean[14:16], [1., -1.])
    np.testing.assert_array_equal(scales[14:16], 1e-5)
    np.testing.assert_array_equal(scales[:14], 1.)
    np.testing.assert_array_equal(mean[:14], 0.)
    assert np.all(groups == -1)


def test_linear_bias_replays_generator_rng_order(truth):
    rng = np.random.default_rng(219)
    rng.normal(size=23); rng.uniform(size=2)
    expected = 300 * rng.normal(size=3)
    np.testing.assert_array_equal(generating_linear_bias(truth, 3), expected)


@pytest.mark.parametrize('known,fraction', [(['unknown'], 1e-5), ([], 0), ([], np.nan)])
def test_invalid_conditional_contract_rejected(truth, known, fraction):
    with pytest.raises(ValueError):
        conditional_prior(truth['coordinate_widths'], False, [1., -1.], [2., 3.], truth, known, fraction)
