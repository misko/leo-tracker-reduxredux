import json
from pathlib import Path
import unittest

class ControlledMatrix(unittest.TestCase):
    def test_long_budget_uses_own_primary_selection(self):
        r=json.loads((Path(__file__).parent/'results.json').read_text())
        long=json.loads((Path(__file__).parent/'long_budget.json').read_text())
        self.assertEqual(long['sigma_s'],1)
        self.assertEqual(long['maximum_seconds'],60)
        self.assertEqual(len(long['runs']),2)
        for q in long['runs']:
            primary=next(x for x in r['selections'] if x['domain']=='original' and x['arm']==q['arm'])
            self.assertEqual(q['start']['vector'],primary['vector'])
            self.assertTrue(q['independent_audit']['feasible'])
            self.assertTrue(q['converged'])
            self.assertLessEqual(q['objective'],q['initial_objective']+1e-6)
    def test_matrix_and_nested_domains(self):
        r=json.loads((Path(__file__).parent/'results.json').read_text())
        self.assertEqual(r['sigma_s'],1)
        self.assertEqual(len(r['runs']),36)
        matrix={(q['result']['basin'],q['result']['arm'],q['result']['domain'],q['result']['origin']) for q in r['runs'] if q['result']['origin'].startswith('original-')}
        self.assertEqual(len(matrix),32)
        for q in r['runs']:
            self.assertTrue(q['result']['feasible'])
            self.assertEqual(q['start']['arm'],q['result']['arm'])
            if q['result']['arm']=='zero-c':self.assertEqual(q['result']['vector'][6],0)
        for selected in r['selections']:
            wanted=min(q['selection_score'] for q in r['candidates'] if q['domain']==selected['domain'] and q['arm']==selected['arm'] and q['feasible'])
            self.assertEqual(selected['selection_score'],wanted)

if __name__=='__main__':unittest.main()
