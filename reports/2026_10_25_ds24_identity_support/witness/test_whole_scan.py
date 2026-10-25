import unittest
import whole_scan as m


class WholeScanTests(unittest.TestCase):
    def row(self):return dict(receiver='RX2',canonical_curved=True,original_accepted_ID_overlap=dict(c0=[],fitted_c=[]),reused_reference_IDs=[],primary_eligible=False)

    def test_time_primary_failure_does_not_block_whole_scan(self):
        self.assertTrue(m.classify(self.row())['whole_scan_eligible'])

    def test_either_arm_complete_ownership_still_blocks(self):
        row=self.row();row['original_accepted_ID_overlap']['c0']=['old']
        self.assertFalse(m.classify(row)['whole_scan_eligible'])

    def test_noncurved_secondary_does_not_enter_curved_whole_scan_pool(self):
        row=self.row();row['canonical_curved']=False
        self.assertFalse(m.classify(row)['whole_scan_eligible'])

    def test_CFO_identity_and_alias_do_not_change_selection(self):
        row=self.row()
        self.assertEqual(m.classify(row),m.classify(dict(row,values=[-1e12],candidate_norad=60108,alias=4)))


if __name__=='__main__':unittest.main()
