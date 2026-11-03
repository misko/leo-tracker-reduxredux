"""Audit invariants for recorded numerical experiments; no optimizer rerun."""
import json,unittest
from pathlib import Path

class ReceiptTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.r=json.loads((Path(__file__).parent/'results.json').read_text())
    def test_frozen_objectives_reconstruct(self):
        deltas=[p['archived_delta'] for p in self.r['points'] if p['archived_delta'] is not None]
        self.assertEqual(len(deltas),8)
        self.assertLess(max(map(abs,deltas)),1e-8)
    def test_numerical_checks_classify_discontinuities(self):
        self.assertEqual(len(self.r['points']),16)
        for p in self.r['points']:
            self.assertEqual(len(p['checks']),21)
            self.assertTrue(all(c['visibility_crossings']==0 for c in p['checks']))
            smooth=[c for c in p['checks'] if c['knot_crossings']==0]
            self.assertTrue(smooth)
            self.assertLess(max(c['normalized_error'] for c in smooth),.001)
    def test_bad_near_is_positive_curvature_at_both_scales(self):
        p=next(p for p in self.r['points'] if p['basin']=='point:-87.5:-87.5' and p['label']=='saved:fitted-c:associated')
        self.assertLess(p['scaled_gradient_max'],.001)
        self.assertEqual(len(p['curvature']),2)
        self.assertTrue(all(min(c['eigenvalues'])>20 for c in p['curvature']))
        path=self.r['paths']
        self.assertGreater(path[1]['objective']-path[0]['objective'],400)
        self.assertLess(path[-1]['objective'],path[0]['objective']-2000)

if __name__=='__main__':unittest.main()
