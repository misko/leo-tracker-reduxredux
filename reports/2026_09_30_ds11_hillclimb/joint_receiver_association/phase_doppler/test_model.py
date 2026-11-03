import unittest
import numpy as np
from model import slope,transfer


class ResidualTests(unittest.TestCase):
    def test_slope_training_isolation(self):
        t=np.linspace(0,10,20);y=35+4*t;mask=np.arange(20)%2==0
        a=slope(t,y,mask);y[~mask]+=1000;b=slope(t,y,mask)
        self.assertTrue(a['qualified']);self.assertAlmostEqual(a['slope_hz_per_s'],4.)
        self.assertEqual(a,b)

    def test_transfer_frozen_before_validation(self):
        train=[dict(phase_residual=i*.01,training_slope=3+2*i,held_slope=3+2*i) for i in range(7)]
        a=transfer(train,train);self.assertTrue(a['passed'])
        b=transfer(train,[dict(r,held_slope=r['held_slope']+500) for r in train])
        self.assertEqual(a['parameters'],b['parameters']);self.assertFalse(b['passed'])
