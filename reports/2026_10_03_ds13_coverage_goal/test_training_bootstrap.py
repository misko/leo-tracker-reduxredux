import unittest
from types import SimpleNamespace
import numpy as np
from training_bootstrap import training_view,histogram_modes
from benchmark import ALIAS_HZ


class BootstrapTests(unittest.TestCase):
    def test_heldout_measurements_do_not_enter_training_view(self):
        d=SimpleNamespace(numbers=np.arange(4),initial=np.ones(10))
        for key in ('times','measured','rf','receiver','channel','group','margin'):
            setattr(d,key,np.arange(6,dtype=float))
        mask=np.array([1,1,0,0,1,0],bool);v=training_view(d,mask)
        d.measured[~mask]=1e20;w=training_view(d,mask)
        np.testing.assert_array_equal(v.measured,w.measured)
        np.testing.assert_array_equal(v.original_rows,[0,1,4])
        self.assertTrue(np.all(v.initial==0));self.assertTrue(np.all(d.initial==1))

    def test_periodic_histogram_finds_seam_peak(self):
        centers=np.linspace(-ALIAS_HZ/2,ALIAS_HZ/2,910,endpoint=False)
        h=np.zeros(910);h[0]=100;h[-1]=90
        best=histogram_modes(h,centers)[0]
        self.assertEqual(best['offset_hz'],centers[0])


if __name__=='__main__':unittest.main()
