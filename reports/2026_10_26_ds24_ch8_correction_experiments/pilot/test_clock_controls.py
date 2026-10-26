import unittest
import numpy as np
from clock_controls import control
from response import compare, synthetic
from frequency_selective_pilot import ChannelPilotWorkspace


class ClockControls(unittest.TestCase):
    def test_analytic_unknown_channel_and_noise_recovers_received_rate(self):
        result = control()
        self.assertGreater(result['descriptive_frame_bootstrap_95_interval'][0],.01)
        for fit in result['models']['received_rate']['fits']:
            self.assertAlmostEqual(fit['received_symbol_rate_ppm'],37.,delta=1.)
            self.assertAlmostEqual(fit['residual_cfo_hz'],23.4,delta=1.)
            self.assertFalse(fit['boundary'])

    def test_held_symbol_prediction_matches_existing_implementation(self):
        y, rate, edge, epoch, cfo = synthetic(119,size=20000)
        y = y*np.exp(-2j*np.pi*cfo*np.arange(len(y))/rate)
        workspace = ChannelPilotWorkspace(y,rate,edge,epoch)
        result = compare(y,rate,edge,epoch,0.)
        for name,flat in [('flat',True),('per_tone',False)]:
            errors = []
            for subset in ('symbol_even','symbol_odd'):
                fit = dict(CFO_hz=0.,offset_samples=0.,modulation_ppm=0.)
                errors.append(workspace.prediction_error(fit,subset,flat=flat)['heldout_squared_error'])
            self.assertAlmostEqual(sum(errors), result['models'][name]['squared_error'],delta=1e-8)


if __name__ == '__main__':
    unittest.main()
