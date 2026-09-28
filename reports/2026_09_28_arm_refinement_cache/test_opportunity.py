import unittest
from opportunity import window_counts


class OpportunityTest(unittest.TestCase):
    def test_exact_keys_and_multiplicity(self):
        candidates=[dict(refined_epoch=1,fine_cfo_hz=1000,acquired_cfo_hz=1001,margin=.1),
                    dict(refined_epoch=1,fine_cfo_hz=1000,acquired_cfo_hz=1001,margin=.1),
                    dict(refined_epoch=1,fine_cfo_hz=1000,acquired_cfo_hz=1001.000001,margin=.1)]
        x=window_counts(candidates)
        self.assertEqual(x['candidates'],3)
        self.assertEqual(x['positive_candidates'],3)
        self.assertEqual(x['repeated_epoch'],2)
        self.assertEqual(x['repeated_epoch_fine_cfo'],2)
        self.assertEqual(x['repeated_epoch_final_cfo'],1)
        self.assertEqual(window_counts(candidates[:1])['repeated_epoch_final_cfo'],0)


if __name__=='__main__':unittest.main()
