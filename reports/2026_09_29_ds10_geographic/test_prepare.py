import unittest
from prepare import select


class SelectionTests(unittest.TestCase):
    def test_order_endpoints_and_nonselection_fields(self):
        rows=[dict(session_id=str(i),capture_start_utc_ns=i,sample_rate_hz=i) for i in range(187)]
        chosen=select(rows[::-1])
        self.assertEqual(len({i for i,_ in chosen}),24)
        self.assertEqual([chosen[0][0],chosen[-1][0]],[0,186])
        for r in rows:r['sample_rate_hz']=-1
        self.assertEqual([i for i,_ in select(rows)],[i for i,_ in chosen])

    def test_duplicates_rejected(self):
        with self.assertRaises(ValueError):select([dict(session_id='same',capture_start_utc_ns=i) for i in range(24)])
