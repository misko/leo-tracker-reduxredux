import unittest
import inventory as m


class MetadataTests(unittest.TestCase):
    def test_closed_overlap_and_exact_grid_adjacency(self):
        owner=dict(start_s=1.,end_s=2.)
        self.assertEqual(m.time_relation(owner,dict(start_s=2.,end_s=3.),[1.,2.,3.])['relation'],'interval_overlap')
        self.assertEqual(m.time_relation(owner,dict(start_s=3.,end_s=4.),[1.,2.,3.,4.])['relation'],'adjacent_native_slices')
        self.assertEqual(m.time_relation(owner,dict(start_s=4.,end_s=5.),[1.,2.,3.,4.,5.])['relation'],'separated')

    def test_one_accepted_ID_blocks_complete_owner_in_either_arm(self):
        owner=dict(receiver='RX2',observation_ids=['a','b'])
        flags=m.classify(owner,True,dict(c0=set(),fitted_c={'b'}),set(),[dict(relation='interval_overlap')])
        self.assertFalse(flags['primary_eligible'])
        self.assertEqual(flags['original_accepted_ID_overlap']['fitted_c'],['b'])

    def test_CFO_candidate_alias_redaction_cannot_change_metadata(self):
        track=dict(key='x',receiver='RX2',channel=1,rf_hz=11e9,times=[1.,2.],observation_ids=['a','b'])
        self.assertEqual(m.metadata(track),m.metadata(dict(track,values=[1e9,-1e9],candidate_norad=60108,alias=4)))

    def test_noncurved_predictive_only_secondary_preserved(self):
        owner=dict(receiver='RX2',observation_ids=['a'])
        flags=m.classify(owner,False,dict(c0=set(),fitted_c=set()),set(),[dict(relation='interval_overlap')])
        self.assertFalse(flags['primary_eligible'])
        self.assertTrue(flags['secondary_noncurved_eligible'])


if __name__=='__main__':unittest.main()
