import unittest

from reports.ALGO08.v3.first30_after_intake import partition, remainder


def clock(seconds):
    return dict(elapsed_s=seconds, cpu_s=seconds)


def witness(*, fallback=False):
    attempt = dict(decision="fallback" if fallback else "complete", cold_clocks=clock(.25),
                   candidate_pre_evidence_clocks=clock(1.))
    if fallback:
        attempt.update(reason="repair_original_joint_pair_gate", fallback_clocks=clock(.8), repair_fit_clocks=clock(.2))
    else:
        attempt.update(signed_total_clocks=clock(.1), exterior_clocks=clock(.05), standard_evidence_clocks=clock(.5))
    return dict(raw_route="optimized_installed_graph", timing=dict(analyze=[clock(3.6)], solve=[clock(2.4)], render=[clock(1.)]),
                ports=dict(history=dict(prepare=[dict(cpu_ns=300_000_000, elapsed_ns=300_000_000)],
                                        infer=[dict(cpu_ns=2_050_000_000, elapsed_ns=2_050_000_000)]),
                           history_risk=dict(choice=dict(route="lean"), lean_attempts=[attempt])))


class PostIntakeAccountingTest(unittest.TestCase):
    def setUp(self):
        self.original = dict(clock(10.4), process=clock(10.), validation=clock(.4))
        self.raw = dict(phases=dict(installed_source_checks=clock(.1), receiver_ready_from_entry=clock(.5),
                                    asset_and_inventory_checks=clock(.2), authenticated_raw_acquisition=clock(5.),
                                    held_anchor_route_selection=clock(.1), decision_and_publication=clock(4.)))

    def test_nonoverlap_through_exit_and_nested_substages(self):
        book = partition(dict(decision="complete"), self.original, self.raw, witness())
        outer, solve, proposal = (book[k]["elapsed_s"] for k in ("outer", "solver", "proposal"))
        self.assertAlmostEqual(5.4, sum(outer.values()))
        self.assertAlmostEqual(2.4, sum(solve.values()))
        self.assertAlmostEqual(1., sum(proposal.values()))
        self.assertAlmostEqual(.4, outer["decision_outside_analyze"])
        self.assertAlmostEqual(.2, outer["other_analyze"])
        self.assertAlmostEqual(.5, solve["accepted_standard_evidence"])

    def test_rejected_attempt_does_not_count_as_accepted_or_remove_fallback(self):
        book = partition(dict(decision="complete"), self.original, self.raw, witness(fallback=True))
        solve = book["solver"]["elapsed_s"]
        self.assertEqual("lean_then_fallback", book["route"])
        self.assertEqual(0., solve["accepted_proposal"])
        self.assertEqual(1., solve["rejected_proposal"])
        self.assertEqual(.8, solve["ordinary_fallback"])
        self.assertEqual(.2, book["repair_refit"]["elapsed_s"])

    def test_inconsistent_observed_envelopes_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "enclosing"):
            remainder(1., .6, .5)
        self.original["validation"] = clock(.3)
        with self.assertRaisesRegex(ValueError, "charged child"):
            partition(dict(decision="complete"), self.original, self.raw, witness())
