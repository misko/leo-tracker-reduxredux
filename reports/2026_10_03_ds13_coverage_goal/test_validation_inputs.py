import unittest
import numpy as np
from validation_inputs import shuffled_peak_sets
from benchmark import ALIAS_HZ,canonical_rows


class ControlInputTests(unittest.TestCase):
    def fixture(self):
        groups=np.repeat(np.arange(12),np.tile([1,2,3],4))
        measured=np.arange(len(groups),dtype=float)*100
        measured[2]=measured[1]+ALIAS_HZ
        return dict(group=groups,times_s=groups.astype(float),receiver=groups//6,
            channel=1+groups%2,rf_hz=11e9+(groups%2)*1e8,measured_hz=measured)

    def test_whole_sets_and_lane_metadata_preserved(self):
        a=self.fixture();b=shuffled_peak_sets(a,np.random.default_rng(3))
        np.testing.assert_array_equal(np.sort(b['source_row']),np.arange(len(a['group'])))
        self.assertEqual(len(b['canonical_rows']),len(canonical_rows(a['measured_hz'],a['group'])[0]))
        for group in np.unique(b['group']):
            rows=np.flatnonzero(b['group']==group);donor=b['source_group'][rows]
            self.assertEqual(len(np.unique(donor)),1)
            np.testing.assert_array_equal(b['measured_hz'][rows],a['measured_hz'][a['group']==donor[0]])
            np.testing.assert_array_equal(b['receiver'][rows],a['receiver'][b['source_row'][rows]])
            np.testing.assert_array_equal(b['channel'][rows],a['channel'][b['source_row'][rows]])
            self.assertTrue(np.all(b['times_s'][rows]==float(group)))

    def test_seed_reproducible(self):
        a=self.fixture()
        b=shuffled_peak_sets(a,np.random.default_rng(2));c=shuffled_peak_sets(a,np.random.default_rng(2))
        for key in b:np.testing.assert_array_equal(b[key],c[key])

    def test_mixed_probe_times_fail_explicitly(self):
        a=self.fixture();a['times_s'][2]+=.1
        with self.assertRaises(ValueError):shuffled_peak_sets(a,np.random.default_rng(0))


if __name__=='__main__':unittest.main()
