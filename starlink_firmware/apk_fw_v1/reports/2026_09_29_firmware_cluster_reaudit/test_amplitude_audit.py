import numpy as np
from amplitude_audit import discrete_density


def test_discrete_density_matches_two_explicit_gaussians_and_receiver_swap():
    x = np.array([[0., 0.], [1., -1.]])
    amplitude = np.array([1., 2.])
    noise = np.array([.5, 1.5])
    density = sum(np.exp(-.5 * np.sum(((x - sign * amplitude) / noise) ** 2, axis=1))
                  / (2 * np.pi * np.prod(noise)) for sign in (-1, 1)) / 2
    np.testing.assert_allclose(discrete_density(x, 2, amplitude, noise), np.log(density))
    np.testing.assert_allclose(discrete_density(x[:, ::-1], 2, amplitude[::-1], noise[::-1]),
                               np.log(density))
