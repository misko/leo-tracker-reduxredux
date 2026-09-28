import hashlib
import json
import math
from pathlib import Path
import unittest
from conservative import SOURCE, score

HERE = Path(__file__).resolve().parent


class Tests(unittest.TestCase):
    def test_geometry_free_receipts(self):
        raw=SOURCE.read_bytes(); source=json.loads(raw)
        saved=json.loads((HERE/'geometry-free-results.json').read_text())
        self.assertEqual(saved['source_sha256'],hashlib.sha256(raw).hexdigest())
        self.assertEqual(saved['core_sha256'],hashlib.sha256((HERE/'conservative.py').read_bytes()).hexdigest())
        self.assertEqual(saved['code_sha256'],hashlib.sha256((HERE/'geometry_free_controls.py').read_bytes()).hexdigest())
        lookup={(r['session_id'],r['track_id'],r['direction']):r for r in source['records']}
        self.assertEqual(len(lookup),688)
        for direction,arms in saved['results'].items():
            for mode,result in arms.items():
                rows=result['records'];self.assertEqual(len(rows),344)
                self.assertEqual(len({(r['session_id'],r['track_id']) for r in rows}),344)
                for r in rows:
                    original=lookup[r['session_id'],r['track_id'],direction]
                    v=original['normal'];p=v['baseline_conditioning_posterior']['log_weights']
                    q=[-math.log(len(p))]*len(p) if mode=='uniform' else v['training_prior']['log_weights']
                    rebuilt=score(p,q,original['held_frequency_log_likelihood'],original['held_count'],.5)
                    for k,value in rebuilt.items():self.assertAlmostEqual(r[k],value,places=12)
                weighted=math.fsum(r['weight']*r['gain'] for r in rows)/sum(r['weight'] for r in rows)
                self.assertAlmostEqual(result['weighted_gain'],weighted,places=12)


if __name__=='__main__': unittest.main()
