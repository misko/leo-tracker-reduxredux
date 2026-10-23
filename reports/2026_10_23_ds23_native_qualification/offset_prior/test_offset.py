import unittest,json
import numpy as np
from run_offset import estimate,OUT

class OffsetTests(unittest.TestCase):
    def test_known_variance_subtracted_not_raw_RMS(self):
        rows=[dict(arm='c0',mean_error_hz=100,shared_mean_variance_hz2=9000,noise_mean_variance_hz2=1000)]*3
        result=estimate(rows,'c0')
        self.assertEqual(result['method_of_moments_variance_hz2'],0)
        self.assertEqual(result['marginal_pseudolikelihood_best_sd_hz'],0)
    def test_saved_selection_and_convergence(self):
        d=json.loads((OUT/'results.json').read_text());rows=d['rows']
        self.assertEqual(len(rows),24)
        self.assertTrue(all(r['phase_converged'] for r in rows))
        self.assertEqual(len({(r['case'],r['family']) for r in rows}),12)
        for r in rows:
            self.assertGreater(r['shared_mean_variance_hz2'],0)
            self.assertGreater(r['noise_mean_variance_hz2'],0)
        self.assertEqual([len(v['selected']) for v in d['inventory']],[4,2,6])

if __name__=='__main__':unittest.main()
