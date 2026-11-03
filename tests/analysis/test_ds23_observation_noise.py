from pathlib import Path
import sys
import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]/'tools'))
from ds23_observation_noise import observation_bound, noise_partition
from dsx01_hierarchical_bound import hierarchical_bound


@pytest.mark.parametrize('block_points', [None, 1, 4])
def test_sparse_owner_algorithm_matches_existing_normalized_group_bound(block_points):
    rng = np.random.default_rng(8181)
    owners = np.repeat([0, 1, 2], [12, 7, 9]); n = len(owners)
    u = rng.normal(size=(n, 7)); u[owners != 0, 4] = 0; u[owners != 1, 5] = 0; u[owners != 2, 6] = 0
    y = rng.normal(size=n); y[-1] += 5
    sigma = rng.uniform(.5, 2., n); groups = noise_partition(owners, block_points)
    powers = rng.uniform(.4, 1., int(groups.max())+1)
    prior = np.array([-1, 0, 0, 1, -1, -1, -1])
    first = hierarchical_bound(y, u, sigma, groups, powers=powers, prior_groups=prior)
    second = observation_bound(y, u, sigma, groups, owners, powers=powers, prior_groups=prior)
    for k in ['coefficient', 'noise_precision', 'coefficient_prior_precision', 'negative_twice_elbo',
              'normalization_constant', 'quadratic', 'logvolume', 'gamma_cost']:
        np.testing.assert_allclose(second[k], first[k], rtol=2e-10, atol=2e-10)


def test_point_noise_does_not_let_one_outlier_deflate_all_other_precisions():
    y = np.r_[np.tile([-.1, 0., .1], 10), 15.]
    u = np.ones((len(y), 1)); owners = np.zeros(len(y), int)
    grouped = observation_bound(y, u, 1., owners, owners)
    point = observation_bound(y, u, 1., np.arange(len(y)), owners)
    assert point['noise_precision'][-1] < .05
    assert np.median(point['noise_precision'][:-1]) > .9
    assert grouped['noise_precision'][0] < .2


def test_noise_blocks_never_cross_fragment_boundaries_even_for_remainders():
    owners = np.repeat([0, 1, 2], [5, 3, 9]); groups = noise_partition(owners, 4)
    assert len(np.unique(groups)) == 6
    for k in np.unique(groups):
        assert len(np.unique(owners[groups == k])) == 1
