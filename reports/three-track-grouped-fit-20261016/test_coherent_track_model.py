"""Component tests for normalized track density and analytic derivatives."""
import unittest
import numpy as np
from coherent_track_model import coherent_density
from coherent_track_model import CoherentTrackModel
from types import SimpleNamespace
from leo.analysis.regional_position_score import ALIAS_HZ


class CoherentDensityTests(unittest.TestCase):
    def test_one_identity_spans_all_rows(self):
        measured = np.array([0., 100.])
        predicted = np.array([[0., 500., 90.], [600., 100., 10.]])
        value, probability, gradient, _, residual = coherent_density(measured, predicted, np.ones((2, 3)))
        self.assertEqual(int(probability.argmax()), 2)
        self.assertAlmostEqual(float(probability.sum()), 1.)
        np.testing.assert_allclose(gradient, -probability[None, :] * residual / 125**2)

    def test_normalized_identical_candidates(self):
        measured = np.array([10., 20., 30.])
        prediction = np.tile(measured[:, None], (1, 4))
        value, probability, _, visibility_gradient, _ = coherent_density(measured, prediction, np.ones((3, 4)))
        self.assertAlmostEqual(value, 3*np.log(125*np.sqrt(2*np.pi)))
        np.testing.assert_allclose(probability, np.full(4, .25))
        np.testing.assert_allclose(visibility_gradient, 0., atol=1e-15)

    def test_frequency_and_visibility_derivatives(self):
        measured = np.array([50., 210., -10.])
        prediction = np.array([[20., 100., -40.], [150., 220., 30.], [-70., -15., 20.]])
        visibility = np.array([[.2, .7, .4], [.4, .3, .9], [.7, .8, .5]])
        result = coherent_density(measured, prediction, visibility)
        for argument, analytic, step in [(prediction, result[2], .001), (visibility, result[3], 1e-6)]:
            for index in np.ndindex(argument.shape):
                hi = argument.copy(); lo = argument.copy(); hi[index] += step; lo[index] -= step
                value_hi = coherent_density(measured, hi, visibility)[0] if argument is prediction else coherent_density(measured, prediction, hi)[0]
                value_lo = coherent_density(measured, lo, visibility)[0] if argument is prediction else coherent_density(measured, prediction, lo)[0]
                self.assertAlmostEqual((value_hi-value_lo)/(2*step), analytic[index], delta=1e-7)

    def test_alias_equivalence_and_visibility_floor(self):
        measured=np.array([0., 10.]);prediction=np.array([[3., 4.], [5., 9.]])
        weight=np.array([[0., 1.], [0., 1.]])
        first=coherent_density(measured,prediction,weight)
        second=coherent_density(measured,prediction+1/4.4e-6,weight)
        self.assertAlmostEqual(first[0],second[0],places=10)
        self.assertTrue(np.isfinite(first[3]).all())
        np.testing.assert_array_equal(first[3][:,0],0.)

    def test_alias_boundary_uses_both_wrapped_images(self):
        measured=np.zeros(2);prediction=np.full((2,2),ALIAS_HZ/2)
        value,_,gradient,_,_=coherent_density(measured,prediction,np.ones((2,2)))
        expected=2*(.5*(ALIAS_HZ/250)**2+np.log(125*np.sqrt(2*np.pi))-np.log(2))
        self.assertAlmostEqual(value,expected,places=7)
        np.testing.assert_allclose(gradient,0.,atol=1e-10)

    def test_invalid_values_rejected(self):
        with self.assertRaises(ValueError):
            coherent_density(np.array([0.]),np.zeros((1,2)),np.ones((1,2)))
        with self.assertRaises(ValueError):
            coherent_density(np.zeros(2),np.zeros((2,2)),np.full((2,2),np.nan))

    def test_groups_complement_background_without_duplicates(self):
        background=SimpleNamespace(mask=np.array([False,True,False]),
                                   observations=SimpleNamespace(times_s=np.arange(3)))
        CoherentTrackModel(background,[np.array([0,2])])
        for groups in [[np.array([0,0])],[np.array([0,1])],[np.array([0,3])]]:
            with self.assertRaises(ValueError):
                CoherentTrackModel(background,groups)


if __name__ == '__main__':
    unittest.main()
