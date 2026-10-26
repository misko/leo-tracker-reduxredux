import unittest
import numpy as np
import run


class SingleSourceTests(unittest.TestCase):
    def test_schedule_and_one_source(self):
        self.assertEqual(run.VISITS,tuple(range(24)))
        self.assertEqual(run.SOURCE['epoch'],127)
        self.assertEqual(run.SOURCE['rate'],200.)
        self.assertEqual(run.SOURCE['amplitude'],1000.)

    def test_reproducible_quantized_stream(self):
        a,x=run.synthesize(0);b,y=run.synthesize(0)
        np.testing.assert_array_equal(a,b)
        self.assertEqual(x,y);self.assertEqual(a.shape,(200000,2,2))
        self.assertEqual(x['source_count'],1);self.assertEqual(x['clipping_samples'],0)
        self.assertFalse(np.array_equal(a[:,0],a[:,1]))

    def test_different_visit_noise(self):
        _,a=run.synthesize(0);_,b=run.synthesize(1)
        self.assertNotEqual(a['noise_sha256'],b['noise_sha256'])
        self.assertNotEqual(a['iq_sha256'],b['iq_sha256'])

    def test_integrated_linear_carrier(self):
        t=7.125;dt=1e-8
        c=run.fixture.carrier(run.SOURCE,np.array([t,t+dt]))
        frequency=np.angle(c[1]/c[0])/(2*np.pi*dt)
        self.assertAlmostEqual(frequency,100000+200*(t+dt/2),delta=.1)
        with self.assertRaises(ValueError):run.synthesize(24)


if __name__=='__main__':unittest.main()
