import unittest
from types import SimpleNamespace
import numpy as np
from replacement import inject,PERIOD


class ReplacementTests(unittest.TestCase):
    def fixture(self):
        tracks=[dict(key='owner',times=np.array([1.,2.]),values=np.array([10.+PERIOD,20.-2*PERIOD]),observation_ids=['a','b'])]
        return dict(scan=SimpleNamespace(tracks=tracks,fixed_window_noise={'a':40.,'b':50.}),
            observations=[dict(observation_id='a',measured_cfo_hz=10.),dict(observation_id='b',measured_cfo_hz=20.)],
            node={'aliases':[2]},keep=np.array([True,True]),powers=np.array([1.]),means=np.array([0.]),model={'nu':3},entries=[])

    def row(self,delta=0.,qualified=True):
        return dict(native_observation_id='a',original_cfo_hz=10.,corrected_cfo_hz=10.+delta,numerical_frequency_qualified=qualified)

    def test_zero_delta_and_source_nonmutation(self):
        d=self.fixture();new,receipt=inject(d,[self.row()],['a'])
        self.assertTrue(np.array_equal(new['scan'].tracks[0]['values'],d['scan'].tracks[0]['values']))
        self.assertTrue(receipt['zero_delta']);self.assertIsNot(new['scan'].tracks[0]['values'],d['scan'].tracks[0]['values'])

    def test_signed_delta_preserves_alias_offset_and_nonselected(self):
        for delta in (-19.3,18.7):
            d=self.fixture();new,r=inject(d,[self.row(delta)],['a'])
            self.assertAlmostEqual(new['scan'].tracks[0]['values'][0],10.+PERIOD+delta)
            self.assertEqual(new['observations'][0]['measured_cfo_hz'],10.+delta)
            self.assertEqual(new['scan'].tracks[0]['values'][1],20.-2*PERIOD)
            self.assertEqual(d['observations'][0]['measured_cfo_hz'],10.)
            self.assertEqual(r['coordinate_rows'][0]['integer_graph_lift'],1)

    def test_duplicate_missing_wrong_original_and_unqualified_refused(self):
        d=self.fixture()
        for rows,ids in (([self.row(),self.row()],['a']),([self.row()],['a','b']),
                         ([dict(self.row(),original_cfo_hz=9.)],['a']),([self.row(1.,False)],['a'])):
            with self.assertRaises(ValueError):inject(d,rows,ids)
        new,_=inject(d,[self.row(0.,False)],['a']);self.assertEqual(new['observations'],d['observations'])

    def test_noninteger_graph_coordinate_refused(self):
        d=self.fixture();d['scan'].tracks[0]['values'][0]+=.1
        with self.assertRaises(ValueError):inject(d,[self.row()],['a'])


if __name__=='__main__':unittest.main()
