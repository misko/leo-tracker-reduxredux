import json,unittest
from pathlib import Path

class MatchedReceiptTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.r=json.loads((Path(__file__).parent/'results.json').read_text())
    def test_original_basins_completed(self):
        self.assertEqual(self.r['status'],'complete')
        self.assertEqual(len(self.r['basins']),6)
        self.assertEqual(len(self.r['runs']),72)
        self.assertEqual(len(self.r['selections']),12)
        self.assertTrue(all(run['error'] is None for run in self.r['runs']))
    def test_own_arm_original_seed_reused_across_options(self):
        for run in self.r['runs']:
            seed=self.r['basins'][run['basin']]['seeds'][run['arm']]
            self.assertEqual(run['seed_sha256'],seed['vector_sha256'])
            self.assertGreater(run['fit_budget_seconds'],0)
            self.assertLessEqual(run['fit_budget_seconds'],12)
    def test_repricing_and_selection(self):
        discrepancies=[r['discrepancy'] for b in self.r['basins'].values() for r in b['repricing']]
        self.assertEqual(len(discrepancies),24)
        self.assertEqual(max(discrepancies),0)
        for selected in self.r['selections']:
            pool=[r for r in self.r['candidates'] if r['option']==selected['option'] and r['arm']==selected['arm']]
            self.assertTrue(selected['feasible'])
            self.assertTrue(selected['converged'])
            self.assertFalse(selected['boundary'])
            self.assertEqual(selected['selection_score'],min(r['selection_score'] for r in pool))
            if selected['arm']=='zero-c':self.assertEqual(selected['vector'][6],0)

if __name__=='__main__':unittest.main()
