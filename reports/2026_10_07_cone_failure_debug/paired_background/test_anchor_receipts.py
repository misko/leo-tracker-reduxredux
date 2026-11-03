import json,unittest
from pathlib import Path
import numpy as np

class AnchorReceipts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.r=json.loads((Path(__file__).parent/'anchor_results.json').read_text())
    def test_twenty_four_matched_new_runs_completed(self):
        self.assertEqual(self.r['status'],'complete')
        self.assertEqual(sum(len(c['runs']) for c in self.r['cases']),24)
        for case in self.r['cases']:
            for arm in ('fitted-c','zero-c'):
                for anchor in ('anchor-rx0','anchor-rx1'):
                    runs=[r for r in case['runs'] if r['arm']==arm and r['origin']==anchor]
                    self.assertEqual(len(runs),3)
                    self.assertEqual(len({r['seed_sha256'] for r in runs}),1)
                    self.assertTrue(all(r['converged'] and r['feasible'] for r in runs))
                    if arm=='zero-c':self.assertTrue(all(r['vector'][6]==0 for r in runs))
    def test_initializer_preserves_anchor_and_nonclock_parameters(self):
        for case in self.r['cases']:
            for arm,receipt in case['initializers'].items():
                original=np.array(receipt['original_vector'])
                for anchor,row in receipt['anchors'].items():
                    v=np.array(row['vector']);held=[2,3] if anchor=='anchor-rx0' else [4,5]
                    np.testing.assert_array_equal(v[held],original[held])
                    np.testing.assert_array_equal(v[:2],original[:2])
                    np.testing.assert_array_equal(v[6:],original[6:])
    def test_selection_uses_scores_and_nonstationarity_is_retained(self):
        for case in self.r['cases']:
            for selected in case['selections']:
                pool=[r for r in case['candidates'] if r['model']==selected['model'] and r['arm']==selected['arm']]
                self.assertEqual(selected['selection_score'],min(r['selection_score'] for r in pool))
                self.assertTrue(selected['feasible'])
        case=next(c for c in self.r['cases'] if c['case']=='2139')
        independent=next(r for r in case['selections'] if r['model']=='independent' and r['arm']=='fitted-c')
        self.assertFalse(independent['converged'])

if __name__=='__main__':unittest.main()
