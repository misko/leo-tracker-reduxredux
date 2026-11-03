"""Independent quadrature and finite-difference checks for marginal density."""
import unittest

import numpy as np

from offset_marginal_density import density, _quadrature_pdf


class MarginalTests(unittest.TestCase):
    def test_odd_degree_density_against_quadrature(self):
        residual = np.array([-110000., -500., -31., 0., 25., 700., 110000.])
        for df in [9., 11.]:
            for scale in [20., 100., 400.]:
                for noise in [1., 10., 50.]:
                    actual = density(residual, 250000., scale, df, noise)[0]
                    expected = _quadrature_pdf(residual, 250000., scale, df, noise)
                    np.testing.assert_allclose(actual, expected, rtol=2e-6, atol=1e-13)

    def test_derivatives(self):
        residual = np.array([-80., -10., 0., 30., 200.])
        for df in [9., 10., 11.]:
            for noise in [0., 5., 35.]:
                _, dr, ds = density(residual, 250000., 50., df, noise)
                h = .005
                numeric_r = (density(residual+h, 250000., 50., df, noise, derivatives=False)[0]
                             -density(residual-h, 250000., 50., df, noise, derivatives=False)[0])/(2*h)
                numeric_s = (density(residual, 250000., 50.+h, df, noise, derivatives=False)[0]
                             -density(residual, 250000., 50.-h, df, noise, derivatives=False)[0])/(2*h)
                np.testing.assert_allclose(dr, numeric_r, rtol=2e-5, atol=1e-10)
                np.testing.assert_allclose(ds, numeric_s, rtol=2e-5, atol=1e-10)

    def test_normalization_and_periodicity(self):
        x = np.linspace(-125000., 125000., 200001)
        for noise in [0., 5., 50.]:
            y = density(x, 250000., 50., 11., noise)[0]
            self.assertLess(abs(np.trapezoid(y, x)-1), 1e-8)
            np.testing.assert_allclose(density(np.array([25., 250025.]), 250000., 50., 11., noise)[0],
                                       [density(25., 250000., 50., 11., noise)[0]]*2)


if __name__ == '__main__':
    unittest.main()
