import types
import unittest
from screen_timing_priors import check_split,decompose


class TimingPriorScreenTests(unittest.TestCase):
    def test_test_and_validation_scans_locked(self):
        cohort={'scans':[{'label':'D','split':'development'},{'label':'T','split':'locked_test'},
                         {'label':'V','split':'validation'}]}
        check_split(cohort,'D')
        for label in ('T','V','missing'):
            with self.assertRaisesRegex(ValueError,'development'):check_split(cohort,label)

    def test_likelihood_and_penalty_are_separate(self):
        obj=types.SimpleNamespace(size=2,evaluate=lambda v:(13.,None),
                                  base=types.SimpleNamespace(penalty=lambda v:(3.,None)))
        record={'vector':[0.,1.,2.],'objective':13.}
        self.assertEqual(decompose(obj,record),{'data_nll':10.,'timing_penalty':3.})
        record['objective']=14.
        with self.assertRaisesRegex(ValueError,'reconstruct'):decompose(obj,record)
