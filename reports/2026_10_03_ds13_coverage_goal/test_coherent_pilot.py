import unittest
import numpy as np
from coherent_pilot import fit_frames,compare_frames


class CoherentPilotTests(unittest.TestCase):
    def test_close_sources_resolved_in_coherent_synthetic_example(self):
        times=np.arange(15)[:,None]/750+np.arange(64)[None,:]*4.4e-6
        freq=[30.,75.];x=np.exp(2j*np.pi*times[:,:,None]*np.array(freq));y=x@np.array([2+1j,1-1j])
        result=compare_frames(y,np.ones(64),times,np.arange(15)%2==0,freq)
        self.assertLess(result['two_test_sse'],1e-20)
        self.assertGreater(result['one_test_sse'],1.)

    def test_test_frames_do_not_change_training_parameters(self):
        x=np.ones((6,10,1),complex);y=np.ones((6,10),complex)*3;train=np.arange(6)%2==0
        before=fit_frames(y,x,train);y[~train]=100;after=fit_frames(y,x,train)
        np.testing.assert_allclose(before[2],after[2]);self.assertEqual(before[0],after[0])
        self.assertGreater(after[1],before[1])

    def test_refined_frequency_ignores_test_frame_values(self):
        times=np.arange(10)[:,None]/750+np.arange(16)[None,:]*4.4e-6
        y=np.exp(2j*np.pi*times*34.56);train=np.arange(10)<5
        before=compare_frames(y,np.ones(16),times,train,[30.,45.],refine=True)
        y[~train]*=100j
        after=compare_frames(y,np.ones(16),times,train,[30.,45.],refine=True)
        self.assertAlmostEqual(before['one_cfo_hz'],34.56,places=2)
        self.assertEqual(before['one_cfo_hz'],after['one_cfo_hz'])


if __name__=='__main__':unittest.main()
