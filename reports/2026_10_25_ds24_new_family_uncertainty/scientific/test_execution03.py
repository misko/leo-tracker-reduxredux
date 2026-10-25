"""Original gate regression and unchanged bounded runner tests; no fits."""

import copy
import unittest
from unittest.mock import patch

import adapter as a
import execution03 as e
import recovery as r
from test_execution02 import RunnerTests as OriginalRunnerTests


class GateRegressionTests(unittest.TestCase):
    def summary(self):
        return dict(gates=dict(tracks=[dict(compatible=True)]), linear_gates=[],
                    endpoint_east_north_km=[0., 0.], state=dict(phases=[14.]))

    def test_absolute_phase_cannot_hide_behind_clipped_reference(self):
        summary = self.summary()
        self.assertTrue(e.original_single_arm_valid(summary, 0.))
        summary['state']['phases'] = [15.000002]
        self.assertFalse(e.original_single_arm_valid(summary, 0.))
        summary['state']['phases'] = [-15.000002]
        self.assertFalse(e.original_single_arm_valid(summary, 0.))

    def test_all_original_single_arm_predicates(self):
        summary = self.summary()
        variants = []
        for key, value in [('endpoint_east_north_km', [12.6, 0.]),
                           ('endpoint_east_north_km', [float('nan'), 0.]),
                           ('endpoint_east_north_km', [0.]),
                           ('gates', dict(tracks=[])),
                           ('linear_gates', [dict(compatible=False)])]:
            changed = copy.deepcopy(summary); changed[key] = value
            variants.append(changed)
        for changed in variants:
            self.assertFalse(e.original_single_arm_valid(changed, 0.))
        self.assertFalse(e.original_single_arm_valid(summary, .011))

    def test_declared_file_hash_mismatch_blocks_launch(self):
        fake = dict(source_sha256={}, target_bindings_sha256='expected')
        def read(path):
            return fake if path == e.PROTOCOL else dict(protocol_sha256='protocol')
        with patch.object(e.r, 'read', read), patch.object(e.r, 'sha',
                lambda path:'protocol' if path == e.PROTOCOL else 'changed'):
            with self.assertRaisesRegex(ValueError, 'declared frozen file changed'):
                e.verify(require_go=False)

    def test_real_baseline_summary_obeys_original_absolute_phase_gate(self):
        for case in a.CASES:
            d = a.load_context(case)
            for arm in a.ARMS:
                saved = d['arms'][arm]
                p = r.build(d, arm, saved['phase_reference'])
                summary = r.summary(p, saved['endpoint_east_north_km'], d['entries'])
                self.assertTrue(e.original_single_arm_valid(summary, 0.))
                changed = copy.deepcopy(summary)
                changed['state']['phases'][0] = 15.000002
                self.assertFalse(e.original_single_arm_valid(changed, 0.))


if __name__ == '__main__':
    unittest.main()
