import unittest
import numpy as np
from audit import fit_phase
from export import phase_us


class PhaseTests(unittest.TestCase):
    def test_integer_counter_precision(self):
        a=phase_us(10**18+17,0,3,.125,5000000,750)
        b=phase_us((10**18+17)%20000,0,3,.125,5000000,750)
        self.assertAlmostEqual(a,b,places=10)
        self.assertAlmostEqual(phase_us(0,0,0,.125,5000000,750),.025)

    def test_held_cannot_change_training_clock(self):
        t=np.linspace(0,10,51);ranges=3100+18*t+.2*t*t
        phase=(ranges+450+2*t)%(1e6/750)
        mask=np.arange(len(t))%3!=1
        good=fit_phase(t,phase,ranges,mask,1e6/750,1)
        null=fit_phase(t,phase,ranges,mask,1e6/750,0)
        self.assertTrue(good['qualified'])
        self.assertLess(good['held_median_absolute_us'],1e-8)
        self.assertGreater(null['held_median_absolute_us'],.1)
        changed=phase.copy();changed[~mask]+=300
        other=fit_phase(t,changed,ranges,mask,1e6/750,1)
        self.assertEqual(good['phase_origin_us'],other['phase_origin_us'])
        self.assertEqual(good['clock_slope_us_per_s'],other['clock_slope_us_per_s'])
