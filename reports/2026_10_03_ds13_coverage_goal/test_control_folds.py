import unittest
from summarize_control_folds import strict_abstention


class ControlFoldTests(unittest.TestCase):
    def test_honest_abstention(self):
        self.assertTrue(strict_abstention(dict(status='abstain_no_coherent_seed',proposals=[],receiver_has_support=[False,False],modes=[[],[]])))

    def test_seeded_is_not_abstention(self):
        self.assertFalse(strict_abstention(dict(status='seed_proposals')))

    def test_inconsistent_receipt_fails(self):
        with self.assertRaises(ValueError):strict_abstention(dict(status='abstain_no_coherent_seed',proposals=[1],receiver_has_support=[False,False],modes=[[],[]]))
