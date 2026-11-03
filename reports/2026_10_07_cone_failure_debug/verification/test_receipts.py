import json
from pathlib import Path
import unittest
HERE=Path(__file__).resolve().parent

class IndependentReceiptAudit(unittest.TestCase):
    def test_anchor_audit_preserves_failed_stationarity_and_nested_gap(self):
        r=json.loads((HERE/'anchor_audit.json').read_text())
        self.assertEqual(len(r['selected']),12)
        bad=next(x for x in r['selected'] if x['case']=='2139' and x['model']=='independent' and x['arm']=='fitted-c')
        self.assertFalse(bad['independent_audit']['converged'])
        self.assertTrue(bad['origin'].startswith('retained:'))
        zero=next(x for x in r['selected'] if x['case']=='2139' and x['model']=='independent' and x['arm']=='zero-c')
        self.assertLess(zero['error_m'],5000)
        self.assertLess(zero['clock']['median_absolute_residual_hz'],100)
        gap=next(x for x in r['nested_gaps'] if x['case']=='2139' and x['model']=='background')
        self.assertGreater(gap['gap'],200)
    def test_selected_states_and_frozen_input(self):
        r=json.loads((HERE/'audit.json').read_text())
        self.assertEqual(r['paired_input_sha256'],'sha256:cd227b923bd200ea8b3d03ecac4cdff0e47a0587e4b8945caa9be5a0d51dc1f0')
        self.assertEqual(len(r['selected']),24)
        self.assertFalse(r['limitations'])
        for x in r['selected']:
            audit=x['independent_audit']
            self.assertTrue(audit['feasible'])
            self.assertEqual(audit['converged'],audit['stationarity']<=.001)
            self.assertGreater(x['clock']['count'],0)
        for x in r['receipts']:
            self.assertFalse(x['source_hash_mismatches'])
    def test_clock_conflict_is_not_mislabeled_as_a_location_fix(self):
        r=json.loads((HERE/'audit.json').read_text())
        old=next(x for x in r['selected'] if x['case']=='2139' and x['family']=='paired_identity' and x['option']=='paired' and x['arm']=='zero-c')
        new=next(x for x in r['selected'] if x['case']=='2139' and x['family']=='paired_background' and x['option']=='background' and x['arm']=='zero-c')
        self.assertGreater(old['clock']['median_absolute_residual_hz'],5000)
        self.assertLess(new['clock']['median_absolute_residual_hz'],100)
        self.assertGreater(new['error_m'],10000)
        self.assertGreater(new['error_m'],old['error_m'])

if __name__=='__main__':unittest.main()
