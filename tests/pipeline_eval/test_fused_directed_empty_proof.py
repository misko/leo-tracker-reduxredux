from dataclasses import replace
from math import inf, nextafter
import unittest

from reports.ALGO08.v3.fused_directed_empty_proof import Correlation, RATE, Seed, plan_geometry, query, stencil


def opportunity():
    target = 17_363_572_521_076
    left = dict(counter=target-RATE, integer_epoch_sample=13332, fractional_epoch_offset_samples=.375,
                signed_cfo_hz=-108_000., graph_alias_lift=0)
    right = dict(counter=target+RATE, integer_epoch_sample=100, fractional_epoch_offset_samples=-.375,
                 signed_cfo_hz=-110_000., graph_alias_lift=0)
    return dict(observation_id="example", counter=target, visit_index=17, radio=1,
                status="unique_signed_bracket", brackets=[dict(left=left, right=right, right_weight=.5,
                                                               signed_centers_hz=[-109_000.])])


class FusedDirectedEmptyProofTest(unittest.TestCase):
    def test_exact_reuse_requires_signed_binary64_and_proven_operands(self):
        source = Correlation("lane", "raw-digest", "pilot-digest", "original/exact", Seed(10, -40000., +0.))
        self.assertTrue(source.reusable_with(source))
        changes = [replace(source, iq_sha256=None), replace(source, opportunity_id="other-lane"),
                   replace(source, pilot_sha256="different"), replace(source, arithmetic="residual"),
                   replace(source, seed=Seed(10, nextafter(-40000., inf), +0.)),
                   replace(source, seed=Seed(10, -40000., -0.)), replace(source, seed=Seed(11, -40000., +0.))]
        self.assertTrue(all(not source.reusable_with(change) for change in changes))
        self.assertFalse(changes[0].reusable_with(changes[0]))

    def test_identical_seed_reuses_only_early_rows_and_wrap_centers(self):
        for epoch in (0, 1, 2, 13332, 13331, 8046):
            short = stencil(Seed(epoch, -400., .0), short=True)
            full = stencil(Seed(epoch, -400., .0), short=False)
            self.assertEqual(25, len(short))
            self.assertLessEqual(len(full), 75)
            self.assertLessEqual(70, len(full))
            self.assertLess(short, full)

    def test_future_donor_and_quarter_phase_control_do_not_unlock_reuse(self):
        lane = opportunity()
        wait, same_carrier, quarter = query(lane)
        self.assertEqual(RATE, wait)
        self.assertEqual(same_carrier.signed_hz, quarter.signed_hz)
        self.assertNotEqual(same_carrier.exact_state(), quarter.exact_state())
        geometry = plan_geometry(dict(opportunities={lane["observation_id"]: lane}))
        self.assertEqual(1, geometry["queries"])
        self.assertEqual(0, geometry["same_time_fusible"])
        self.assertEqual(0, geometry["quarter_control_shared_integer_rows"])
        self.assertEqual(0, geometry["exact_retained_stencil_proven"])
        lane["brackets"][0]["right"]["counter"] = lane["counter"]
        with self.assertRaisesRegex(ValueError, "signed bracket"):
            query(lane)
