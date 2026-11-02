"""Research adapter checks for native denominator and residual scope."""
import json, tempfile, unittest
from pathlib import Path
from diagnose import inventory, stats,ROOT,INPUT,CASES,ARMS,read,frozen_published_owners

class DiagnosticsTests(unittest.TestCase):
    def test_native_inventory_counts_unique_owners_and_splits_gaps(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            obs=[dict(observation_id=str(i)) for i in range(6)]
            tr=dict(key='native',receiver=1,channel=1,times=[0,1,2,9,10],observation_ids=['0','1','2','3','4'])
            (root/'observations.json').write_text(json.dumps(obs));(root/'tracks.json').write_text(json.dumps([tr,tr]))
            z=dict(native_path=str(root),baseline_owners={a:{'1':123} for a in ('c0','fitted_c')})
            r=inventory(None,z)
            self.assertEqual(r['arms']['fitted_c'],dict(associated=1,native=6,percent=100/6,graph_unassociated=4,untracked=1))
            self.assertEqual(len(r['longest_unassociated']),2)
            self.assertEqual(r['longest_unassociated'][0]['observation_ids'],('0','2'))
            self.assertEqual(r['longest_unassociated'][0]['span_s'],2)

    def test_residuals_preserve_mean_slope_and_all_points(self):
        r=stats([0,1,2,3,4],[1,3,5,7,9])
        self.assertEqual(r['n'],5);self.assertEqual(r['mean_hz'],5);self.assertEqual(r['slope_hz_s'],2)
        self.assertAlmostEqual(r['rms_hz'],33**.5)

    def test_all_published_coverage_and_fitted_ids_match_frozen_owners(self):
        for case in CASES:
            z=read(INPUT/'inputs'/(case+'.json'));expected=frozen_published_owners(case,z)
            inv=read(ROOT/case/'inventory.json');rows=read(ROOT/case/'track_residuals.json')
            for arm in ARMS:
                with self.subTest(case=case,arm=arm):
                    self.assertEqual(inv['arms'][arm]['associated'],len(expected[arm]))
                    fitted=[o for r in rows if r['arm']==arm for o in r['observation_ids']]
                    self.assertEqual(len(fitted),len(set(fitted)))
                    self.assertEqual(set(fitted),set(expected[arm]))

if __name__=='__main__':unittest.main()
