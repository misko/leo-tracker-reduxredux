import unittest
from fit_family import projected_gradient, screen


class CalibrationGateTests(unittest.TestCase):
    def test_projected_gradient_respects_bound_direction(self):
        self.assertEqual(projected_gradient([0., 1.], [3., -2.], [(0., 1.)] * 2), 0.)
        self.assertEqual(projected_gradient([0., 1.], [-3., 2.], [(0., 1.)] * 2), 3.)

    def test_missing_validation_never_passes(self):
        data = {a: dict(score=0., per_source={}) for a in ('receiver', 'elevation', 'signed')}
        self.assertEqual(screen(data, {}, True)['status'], 'no_validation_donor')

    def test_source_majority_and_controls_both_required(self):
        data = dict(receiver=dict(score=-10., per_source={'a': -4., 'b': -6.}), elevation=dict(score=-9.), signed=dict(score=-8., per_source={'a': -3., 'b': -5.}))
        self.assertTrue(screen(data, dict(swapped=-12., permuted=-11.), True)['passed'])
        self.assertFalse(screen(data, dict(swapped=-7.), True)['passed'])
        self.assertFalse(screen(data, {}, False)['passed'])
        data['signed']['per_source']['b'] = -7.
        self.assertFalse(screen(data, {}, True)['passed'])
