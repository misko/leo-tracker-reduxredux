import itertools
import unittest
import numpy as np
from radio_segmentation import partition

class PartitionTests(unittest.TestCase):
    def test_quadratic_not_split(self):
        t=np.arange(30.)
        self.assertEqual(len(partition(t,1+2*t+3*t*t)['segments']),1)
    def test_step_and_offset_invariance(self):
        t=np.arange(24.);y=3*t+np.where(t<12,0.,2000.)
        p=partition(t,y);q=partition(t+100,y+300000)
        self.assertEqual([(r['start'],r['stop']) for r in p['segments']],[(0,12),(12,24)])
        self.assertEqual(p['segments'],q['segments'])
    def test_exhaustive_two_segments(self):
        t=np.arange(18.);y=np.sin(t)*300+np.where(t<8,0.,1000.)
        p=partition(t,y,maximum_segments=2)
        def sse(a,b):
            v=y[a:b];pred=np.polyval(np.polyfit(t[a:b],v,2),t[a:b]);return float(np.sum((v-pred)**2))
        expected=min([sse(0,18)/10000]+[(sse(0,b)+sse(b,18))/10000+6*np.log(18) for b in range(6,13)])
        self.assertAlmostEqual(p['objective'],expected,places=9)
    def test_no_short_segments(self):
        p=partition(np.arange(8.),np.array([0.]*4+[5000.]*4))
        self.assertEqual(len(p['segments']),1)

if __name__=='__main__':unittest.main()
