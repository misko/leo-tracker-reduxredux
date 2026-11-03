import json,unittest
from pathlib import Path

class QuadraticCausalReceipts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.rows=[json.loads((Path(__file__).parent/(case+'.json')).read_text()) for case in ('1939','2139')]
    def test_zero_extra_parity_and_actual_nonzero_extra_gradients(self):
        for row in self.rows:
            self.assertEqual(len(row['checks']['parity']),2)
            for x in row['checks']['parity']:
                self.assertLess(x['objective_discrepancy'],1e-8)
                self.assertLess(x['old_gradient_max_discrepancy'],1e-9)
            self.assertEqual(len(row['checks']['gradient_checks']),10)
            self.assertTrue(all(x['normalized_error']<.002 for x in row['checks']['gradient_checks']))
    def test_receiver_constant_and_linear_gauges_removed(self):
        for row in self.rows:
            for gauge in row['checks']['gauge']:
                self.assertLess(abs(gauge['sum']),1e-7)
                self.assertLess(abs(gauge['linear_dot']),1e-6)
                self.assertEqual(gauge['peak_hz'],100)
                self.assertEqual(gauge['other_rx_max'],0)
    def test_matched_arm_seeds_sigma_and_convergence(self):
        for row in self.rows:
            self.assertEqual(row['relative_sigma_s'],1)
            self.assertEqual(row['quadratic_coefficient_sigma'],2)
            self.assertEqual(len(row['runs']),4)
            for arm in ('fitted-c','zero-c'):
                runs=[r for r in row['runs'] if r['arm']==arm]
                self.assertEqual(len({r['seed_sha256'] for r in runs}),1)
                for run in runs:
                    self.assertTrue(run['result']['feasible'])
                    self.assertTrue(run['result']['converged'])
                    if arm=='zero-c':self.assertEqual(run['result']['vector'][6],0)

if __name__=='__main__':unittest.main()
