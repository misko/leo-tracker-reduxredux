import unittest
from unittest.mock import patch
import run_arm
from run_arm import selection


class SelectionTests(unittest.TestCase):
    def test_dataset_rate_and_edge_isolation(self):
        rows = [dict(dataset_id=dataset, rate_hz=rate,
                     target=dict(edge=edge), visit_index=i)
                for dataset in ('DS8', 'DS9')
                for rate in (2500000, 5000000)
                for edge in ('lower', 'upper') for i in range(3)]
        selected = selection(rows, 'DS9')
        self.assertEqual([r['visit_index'] for r in selected], [0,2,0,2])
        self.assertTrue(all(r['dataset_id']=='DS9' and r['rate_hz']==2500000
                            for r in selected))
        with self.assertRaises(ValueError):
            selection([r for r in rows if r['target']['edge']=='lower'], 'DS9')

    def test_unit_budget_does_not_change_normal_transport_timeout(self):
        with patch.object(run_arm, 'REMOTE') as remote:
            run_arm.remote_with_unit_budget('cd /tmp/test && ./test_screen', timeout=30)
            remote.assert_called_with('cd /tmp/test && ./test_screen', timeout=120)
            run_arm.remote_with_unit_budget('cat case-0.jsonl', timeout=30)
            remote.assert_called_with('cat case-0.jsonl', timeout=30)


if __name__ == '__main__':
    unittest.main()
