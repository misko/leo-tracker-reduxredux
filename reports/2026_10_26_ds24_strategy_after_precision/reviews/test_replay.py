import unittest
from replay import equal_prior_selection,nominate


class PolicyTests(unittest.TestCase):
    def test_equal_prior_keeps_incumbent_on_tie_and_ignores_unqualified(self):
        def trial(loss,valid):return dict(paired_valid=valid,arms={'c0':{'corrected_selection_loss':loss}})
        self.assertFalse(equal_prior_selection(dict(trials=[trial(1,False),trial(10,True)],baseline_corrected_loss={'c0':10}))[0])
        self.assertTrue(equal_prior_selection(dict(trials=[trial(9,True)],baseline_corrected_loss={'c0':10}))[0])

    def test_owner_control_prefers_other_receiver_after_low_family_quartile(self):
        families=[dict(family=j,paired_score=10-j,has_eligible_owner=True) for j in range(5)]
        owners=[dict(owner=str(j),family=j,paired_score=10-j,eligible=True,receiver=1 if j!=4 else 2) for j in range(5)]
        target,control=nominate(families,owners)
        self.assertEqual(target['family'],0);self.assertEqual(control['family'],4)

    def test_unavailable_owner_is_explicit(self):
        self.assertEqual(nominate([],[]),(None,None))


if __name__=='__main__':unittest.main()
