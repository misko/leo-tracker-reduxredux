import unittest
from types import SimpleNamespace
import numpy as np
from control_data import with_control_observations


class ControlDataTests(unittest.TestCase):
    def test_shuffled_observations_replace_real_values_without_changing_orbits(self):
        original=SimpleNamespace(times=np.array([1.,2.]),margin=np.array([3.,4.]),position=np.ones((2,3)))
        a={k:np.array(v) for k,v in dict(times_s=[10.,20.],measured_hz=[200.,100.],rf_hz=[1e9,1e9],
            receiver=[0,0],channel=[1,1],group=[8,9],source_row=[1,0]).items()}
        view=with_control_observations(original,a)
        np.testing.assert_array_equal(view.measured,[200.,100.]);np.testing.assert_array_equal(view.margin,[4.,3.])
        np.testing.assert_array_equal(original.times,[1.,2.]);self.assertIs(view.position,original.position)
        a['source_row']=np.array([1,1])
        with self.assertRaises(ValueError):with_control_observations(original,a)


if __name__=='__main__':unittest.main()
