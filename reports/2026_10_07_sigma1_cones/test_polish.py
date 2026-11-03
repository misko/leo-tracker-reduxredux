import json
import hashlib
import struct
from pathlib import Path
import unittest
HERE=Path(__file__).resolve().parent

class PolishReceipts(unittest.TestCase):
    def test_both_cases_keep_primary_and_own_seeds(self):
        for case in ('2139','1939'):
            primary=json.loads((HERE/case/'results.json').read_text())
            polished=json.loads((HERE/case/'polished.json').read_text())
            self.assertEqual(polished['runs'],primary['runs'])
            self.assertEqual(polished['primary_selections'],primary['selections'])
            self.assertEqual(len(polished['polish_runs']),6)
            self.assertEqual(len({(q['option'],q['arm']) for q in polished['polish_runs']}),6)
            self.assertGreaterEqual(len(polished['candidates']),len(primary['candidates']))
            for q in polished['polish_runs']:
                own=next(r for r in primary['selections'] if r['option']==q['option'] and r['arm']==q['arm'])
                self.assertEqual(q['basin'],own['basin'])
                wanted='sha256:'+hashlib.sha256(struct.pack('<'+'d'*len(own['vector']),*own['vector'])).hexdigest()
                self.assertEqual(q['seed_sha256'],wanted)
                self.assertTrue(q['result']['feasible'])
                if q['arm']=='zero-c':self.assertEqual(q['result']['vector'][6],0)
            for r in polished['selections']:
                previous=next(q for q in primary['selections'] if q['option']==r['option'] and q['arm']==r['arm'])
                self.assertLessEqual(r['selection_score'],previous['selection_score']+1e-8)
                self.assertEqual(r['selection_score'],min(q['selection_score'] for q in polished['candidates'] if q['option']==r['option'] and q['arm']==r['arm']))

if __name__=='__main__':unittest.main()
