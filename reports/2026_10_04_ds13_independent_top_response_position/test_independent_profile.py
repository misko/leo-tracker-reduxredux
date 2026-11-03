"""Explicit archived-analysis fixture tests; no hardware or database access."""
import json
import unittest
from pathlib import Path
import numpy as np
from profile_top_independent import load_engine
from profile_top_2km import OUT, point_design
from replay import digest


class IndependentProfileTests(unittest.TestCase):
    def test_all_four_cases_independent_and_converged(self):
        result=json.loads((OUT/'independent-summary.json').read_text())
        self.assertEqual({(r['scan'],r['arm']) for r in result['cases']},
                         {(s,a) for s in 'AB' for a in ('fitted-c','zero-c')})
        for r in result['cases']:
            self.assertEqual(r['scan'],r['best']['scan'])
            self.assertEqual(r['arm'],r['best']['arm'])
            self.assertEqual(len(r['cells']),73)
            self.assertTrue(all(p['success'] for p in r['cells']))
            self.assertTrue(r['best']['success'])
            self.assertLessEqual(r['distance_m'],2000.00001)
            self.assertTrue(any(t['success'] for t in r['trials']))
            self.assertLessEqual(r['best']['objective'],r['best_sampled']['objective']+1e-3)
            self.assertLess(abs(r['score_change_after_roof_restart']),1e-3)
            self.assertTrue(all(n['delta_from_best']>-1e-3 for n in r['neighbors_25m']))
            self.assertAlmostEqual(r['delta_score'],r['delta_data_nll']+r['delta_prior_nll'],places=7)
        for path,h in result['source_hashes'].items():
            self.assertEqual(digest(Path(path)),h)

    def test_matched_inputs_and_nested_scores(self):
        for scan in 'AB':
            a,b=(load_engine(scan,arm) for arm in ('fitted-c','zero-c'))
            for field in ('measured','numbers','times','group','original_rows','rf'):
                np.testing.assert_array_equal(getattr(a.data,field),getattr(b.data,field))
            self.assertEqual(len(np.unique(a.data.group)),len(a.data.times))
            self.assertEqual(a.meta['selected_by_arm']['fitted-c'],a.meta['selected_by_arm']['zero-c'])
            for p in point_design():
                key=tuple(np.round([p['east_m'],p['north_m']],5))
                self.assertLessEqual(a.cache[key]['objective'],b.cache[key]['objective']+1e-3)
                self.assertEqual(b.cache[key]['c_hz_per_ghz'],0)

    def test_gradients_and_no_outside_disk_evaluations(self):
        for name in ('analytic-gradient-audit.json','B-analytic-gradient-audit.json'):
            for r in json.loads((OUT/name).read_text()):
                self.assertLess(r['error'],1e-4 if r['index'] in (0,1) else .001)
        for scan in 'AB':
            for arm in ('fitted-c','zero-c'):
                engine=load_engine(scan,arm)
                for r in engine.calls:
                    self.assertLessEqual(np.hypot(r['east_m'],r['north_m']),2000.00001)


if __name__=='__main__':
    unittest.main()
