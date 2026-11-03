import json,unittest
from pathlib import Path

class BranchProbeReceipts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rows=[json.loads((Path(__file__).parent/(case+'.json')).read_text()) for case in ('1939','2139')]
    def test_controls_are_fixed_and_all_runs_complete(self):
        for r in self.rows:
            self.assertEqual(r['status'],'complete')
            self.assertEqual(r['relative_sigma_s'],1)
            self.assertEqual(len(r['runs']),8)
            self.assertEqual(len(r['selections']),8)
            for arm in ('zero-c','fitted-c'):
                runs=[x for x in r['runs'] if x['arm']==arm]
                self.assertEqual(len({x['seed_sha256'] for x in runs}),1)
                self.assertTrue(all(0<x['fit_budget_s']<=16 for x in runs))
    def test_selected_states_are_feasible_stationary(self):
        for r in self.rows:
            for x in r['selections']:
                self.assertTrue(x['feasible'])
                self.assertTrue(x['converged'])
                self.assertFalse(x['boundary'])
                if x['arm']=='zero-c':self.assertEqual(x['vector'][6],0)
    def test_acceptance_uses_full_objective_only(self):
        for r in self.rows:
            for run in r['runs']:
                for p in run['interventions']:
                    if p['accepted']:self.assertLess(p['trial'],p['before']-1e-8)

if __name__=='__main__':unittest.main()
