"""Owned metadata and original-gate tests; no position fits or new targets."""

import unittest

import transfer as t


class TransferTests(unittest.TestCase):
    def test_first_four_are_distinct_and_chronological(self):
        document=t.r.read(t.HERE/'panel.json'); rows=document['panel']
        self.assertEqual(len(rows), 4)
        self.assertEqual(len({row['case'] for row in rows}), 4)
        self.assertEqual([row['case'] for row in rows], ['DS24-0010','DS24-0011','DS24-0012','DS24-0013'])
        self.assertEqual(rows, sorted(rows, key=lambda row:(row['recording_utc_ns'],row['case'],row['source_id'],row['component'])))

    def test_complete_parent_acceptance_including_postfit_is_disjoint(self):
        for row in t.r.read(t.HERE/'panel.json')['panel']:
            parent=t.r.read(row['parent_ledger_path'])
            self.assertEqual(t.r.sha(row['parent_ledger_path']), row['parent_ledger_sha256'])
            self.assertTrue(row['active_curvature_persisted'])
            for arm in t.ARMS:
                full=parent['coverage'][arm]
                self.assertFalse(set(row['observation_ids']) & set(full['accepted_observation_ids']))
                self.assertTrue(set(full['curved_observation_ids']+full['predictive_observation_ids']) <= set(full['accepted_observation_ids']))

    def test_original_phase_and_region_predicates_preserved(self):
        summary=dict(gates=dict(tracks=[dict(compatible=True)]),linear_gates=[],
                     endpoint_east_north_km=[0.,0.],state=dict(phases=[15.000002]))
        self.assertFalse(t.controls.original_single_arm_valid(summary,0.))
        summary['state']['phases']=[1.]
        self.assertTrue(t.controls.original_single_arm_valid(summary,0.))
        summary['endpoint_east_north_km']=[12.6,0.]
        self.assertFalse(t.controls.original_single_arm_valid(summary,0.))


if __name__=='__main__':
    unittest.main()
