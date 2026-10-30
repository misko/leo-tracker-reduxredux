import unittest
from inventory_ds26 import published_ids,residual_stats


class InventoryTests(unittest.TestCase):
    def test_published_selected_excludes_replay_only_and_other_arm(self):
        terminal=dict(selected=dict(arms=dict(fitted_c=dict(associated_ids=['accepted']),c0=dict(associated_ids=['other']))))
        self.assertEqual(published_ids(terminal,'fitted_c'),{'accepted'})

    def test_fallback_includes_exact_published_linear_and_gate_support(self):
        arm=dict(gates=dict(tracks=[dict(observation_ids=['gate'])]),linear_gates=[dict(observation_ids=['linear'])])
        self.assertEqual(published_ids(dict(selected=None,baseline=dict(arms=dict(fitted_c=arm))),'fitted_c'),{'gate','linear'})

    def test_partial_subtraction_recomputes_endpoints_and_retains_gap(self):
        track=dict(observation_ids=['a','b','c','d'],times=[0,1,10,20],values=[0,1,10,20])
        stats=residual_stats(track,{'a','c'})
        self.assertEqual((stats['span_s'],stats['largest_gap_s'],stats['residual_points']),(19,19,2))
        self.assertFalse(stats['wholly_unassociated'])
        self.assertEqual(stats['residual_observation_ids'],['b','d'])
        self.assertIsNone(residual_stats(track,{'a','b','c','d'}))
        self.assertEqual(residual_stats(track,{'a','b','c'})['span_s'],0)

    def test_duplicate_timestamps_and_gap_bounded_runs_are_explicit(self):
        track=dict(observation_ids=['a','b','c','d'],times=[0,0,1,10],values=[0,0,1,10])
        stats=residual_stats(track,set())
        self.assertEqual(stats['duplicate_timestamp_points'],1)
        self.assertEqual(stats['maximum_timestamp_multiplicity'],2)
        self.assertEqual(stats['longest_run_gap_le_2s_span_s'],1)
        self.assertEqual(stats['longest_run_gap_le_2s_points'],3)
        self.assertEqual(stats['runs_gap_le_2s'],2)
        self.assertEqual(stats['longest_run_gap_le_10s_span_s'],10)


if __name__=='__main__':
    unittest.main()
