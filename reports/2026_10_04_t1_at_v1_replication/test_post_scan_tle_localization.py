import unittest
from unittest.mock import patch
from types import SimpleNamespace
import numpy as np
from post_scan_tle_localization import aligned_start


class AlignmentTests(unittest.TestCase):
    def test_alignment_uses_orbits_not_observed_frequency(self):
        old=SimpleNamespace(numbers=np.array([101,202]),owners=np.array([101,101,202,202]),
                            times=np.array([1.,2.,3.,4.]),orbit_offset=np.zeros(2),measured=np.zeros(4))
        new=SimpleNamespace(**vars(old));new.orbit_offset=np.array([.4,-.7])
        parameters=np.r_[np.zeros(6),1.,2.]
        record=dict(parameters=parameters.copy(),point_km=[0.,0.],coefficient=12.)
        def predict(data,p,rows,satellites):
            return data.times[rows]+data.orbit_offset[satellites]+p[6+satellites],None,None
        with patch('post_scan_tle_localization.paired_prediction_jacobian',predict):
            aligned,details=aligned_start(old,new,record)
            new.measured=np.full(4,1e9)
            repeated,_=aligned_start(old,new,record)
        np.testing.assert_allclose(aligned['parameters'][6:],[.6,2.7],atol=1e-6)
        np.testing.assert_array_equal(repeated['parameters'],aligned['parameters'])
        np.testing.assert_array_equal(record['parameters'],parameters)
        self.assertTrue(all(r['alignment_rms_hz']<1e-6 for r in details))

    def test_missing_owner_evidence_does_not_silently_remove_satellite(self):
        old=SimpleNamespace(numbers=np.array([101]),owners=np.array([999]))
        with self.assertRaises(ValueError):aligned_start(old,old,dict(parameters=np.zeros(7)))


if __name__=='__main__':unittest.main()
