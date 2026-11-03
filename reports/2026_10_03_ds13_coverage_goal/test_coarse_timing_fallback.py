import unittest
import numpy as np
from adaptive_discovery import timing_modes,coherent_segments
from coarse_timing_fallback import supported_extension_offsets


class SlowTrackRetrievalTests(unittest.TestCase):
    def test_extension_never_extrapolates_ephemeris(self):
        offsets=supported_extension_offsets(np.array([0.,300.]),np.array([-40.,340.]),-.2)
        self.assertTrue(np.all(abs(offsets)>20))
        self.assertTrue(np.all(offsets-.2>=-40))
        self.assertTrue(np.all(300+offsets-.2<340))
        self.assertEqual(offsets.min(),-39)
        self.assertEqual(offsets.max(),40)

    def test_narrow_timing_votes_can_miss_valid_residual_track(self):
        times=np.arange(20,dtype=float);groups=np.arange(20)
        residual=np.linspace(-190,190,20);rate=100.
        self.assertEqual(timing_modes(residual/rate,groups),[])
        segments=coherent_segments(np.flatnonzero(abs(residual)<=600),times,groups,
                                   np.zeros(20,int),np.ones(20,int),residual)
        self.assertEqual(len(segments),1)
        self.assertEqual(segments[0]['groups'],20)
        self.assertLess(segments[0]['rms_native_hz'],200)

    def test_coarse_fallback_does_not_relax_coherence(self):
        times=np.arange(20,dtype=float)*6
        segments=coherent_segments(np.arange(20),times,np.arange(20),np.zeros(20,int),np.ones(20,int),np.zeros(20))
        self.assertEqual(segments,[])
