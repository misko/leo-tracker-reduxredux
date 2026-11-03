import json
from pathlib import Path
import unittest
HERE=Path(__file__).resolve().parent

class MatchedGateReceipts(unittest.TestCase):
    def test_matrix_seeds_and_incumbent_retention(self):
        total=0
        for case in ('1939','2139'):
            primary=json.loads((HERE/case/'results.json').read_text());polished=json.loads((HERE/case/'polished.json').read_text())
            self.assertEqual(primary['sigma_s'],1)
            self.assertEqual(len(primary['runs']),len(primary['basins'])*6);total+=len(primary['runs'])
            for basin in primary['basins']:
                for arm in ('fitted-c','zero-c'):
                    rows=[r for r in primary['runs'] if r['basin']==basin and r['arm']==arm]
                    self.assertEqual({r['option'] for r in rows},{'control','conditional','absolute2'})
                    self.assertEqual(len({r['seed_sha256'] for r in rows}),1)
            self.assertEqual(primary['runs'],polished['runs'])
            self.assertEqual(primary['selections'],polished['primary_selections'])
            self.assertEqual(len(polished['polish_runs']),6)
            for row in polished['candidates']:
                self.assertTrue(row['feasible'])
                if row['arm']=='zero-c':self.assertEqual(row['vector'][6],0)
            for row in polished['selections']:
                wanted=min(r['selection_score'] for r in polished['candidates'] if r['option']==row['option'] and r['arm']==row['arm'])
                self.assertEqual(row['selection_score'],wanted)
        self.assertEqual(total,60)

if __name__=='__main__':unittest.main()
