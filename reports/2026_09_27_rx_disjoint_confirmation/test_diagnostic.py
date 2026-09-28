import json
import math
from pathlib import Path
import unittest
from diagnose_regressions import analyze,describe


class Tests(unittest.TestCase):
    def test_saved_attribution_closes(self):
        path=Path(__file__).resolve().parent/'disjoint-scan-fw-127d8fc36e804ae2.json'
        shard=json.loads(path.read_text());result=analyze(shard)
        for direction,value in result.items():
            self.assertAlmostEqual(value['positive_contribution']+value['negative_contribution'],value['gain'],places=12)
            self.assertAlmostEqual(sum(r['contribution'] for r in value['split'].values()),value['gain'],places=12)
            for r in value['all_tracks']:
                self.assertAlmostEqual(sum(r['held_likelihood_normalized']),1,places=10)
                self.assertTrue(all(math.isfinite(x) for x in r['shared_id_cfo_other_minus_this_hz'].values()))


if __name__=='__main__':unittest.main()
