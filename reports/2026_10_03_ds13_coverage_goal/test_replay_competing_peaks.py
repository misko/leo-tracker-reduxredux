import unittest
from replay_competing_peaks import select_pairs,sample_visits


class ReplaySelectionTests(unittest.TestCase):
    def test_expanded_sample_is_reproducible_and_visit_exclusive(self):
        rows=[dict(integer_epoch_sample=1,acquired_cfo_hz=100+i,probe_key=[i//2,0,0]) for i in range(40)]
        pairs=[dict(row_index=i,nearest_assigned_row=i+1,frequency_distance_hz=1,frame_epoch_distance_samples=0) for i in range(0,40,2)]
        selected,count=sample_visits(pairs,rows)
        self.assertEqual(count,20);self.assertEqual(len(selected),8)
        self.assertEqual((selected,count),sample_visits(pairs,rows))
        self.assertEqual(len({rows[p['row_index']]['probe_key'][0] for p in selected}),8)

    def test_bounded_distinct_visits_and_probe_zero(self):
        rows=[dict(integer_epoch_sample=1,acquired_cfo_hz=100+i,probe_key=[i//2,0,0]) for i in range(6)]
        pairs=[dict(row_index=i,nearest_assigned_row=i+1,frequency_distance_hz=1,frame_epoch_distance_samples=0) for i in (0,2,4)]
        self.assertEqual(len(select_pairs(pairs,rows,limit=2)),2)
        rows[0]['probe_key'][2]=1
        self.assertEqual(select_pairs(pairs,rows,limit=1)[0]['row_index'],2)
