import unittest
import numpy as np
from types import SimpleNamespace
from run_phase0265 import check_domains, fingerprint


class PhaseDomainTests(unittest.TestCase):
    def test_broader_actual_reference_needs_bank_support(self):
        p=SimpleNamespace(sky={'time_s':np.array([-20.,40.])}, flat_times=np.array([0.,10.]), flat_labels=np.array([0,0]))
        self.assertTrue(check_domains(p, np.array([-15.2]), [])['curved']['in_domain'])
        with self.assertRaisesRegex(ValueError, 'causal orbit bank'):
            check_domains(p, np.array([-20.]), [])

    def test_frozen_mask_digest_detects_membership_changes(self):
        self.assertEqual(fingerprint([True,False]), fingerprint(np.array([1,0])))
        self.assertNotEqual(fingerprint([True,False]), fingerprint([False,True]))


if __name__=='__main__': unittest.main()
