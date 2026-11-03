import unittest
from additional_plan import select


class SelectionTests(unittest.TestCase):
    def test_exclusion_order_and_outcome_independence(self):
        rows = [dict(session_id=str(i), capture_start_utc_ns=i, error=100-i) for i in range(20)]
        a = select(rows, {'0', '19'}, 4)
        b = select([dict(r, error=-r['error']) for r in reversed(rows)], {'0', '19'}, 4)
        self.assertEqual([r['session_id'] for r in a], ['1', '6', '12', '18'])
        self.assertEqual([r['session_id'] for r in a], [r['session_id'] for r in b])


if __name__ == '__main__':
    unittest.main()
