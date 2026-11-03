import unittest
from model import summarize


class TradeoffTests(unittest.TestCase):
    def test_failure_is_not_imputed_or_hidden(self):
        rows=[dict(session='a',qualified=True,baseline_qualified=True,error_m=90,baseline_error_m=100),
              dict(session='b',qualified=False,baseline_qualified=False,error_m=None,baseline_error_m=None)]
        out=summarize(rows)
        self.assertIsNone(out['full_panel_metrics']);self.assertEqual(out['attempts'],2)
        self.assertEqual(out['matched_qualified'],1);self.assertEqual(len(out['missing']),1)
        self.assertEqual(out['matched_only_metrics']['paired_wins'],1)

    def test_duplicate_and_invalid_qualified_rows_rejected(self):
        row=dict(session='a',qualified=True,baseline_qualified=True,error_m=1,baseline_error_m=2)
        with self.assertRaises(ValueError):summarize([row,row])
        with self.assertRaises(ValueError):summarize([dict(row,error_m=float('nan'))])
