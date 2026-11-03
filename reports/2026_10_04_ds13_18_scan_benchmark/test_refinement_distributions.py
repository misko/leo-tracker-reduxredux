import unittest
from refinement_distributions import canonical_rows,pair_histogram


class RefinementDistributionTests(unittest.TestCase):
    def test_original_exact_alias_copies_only(self):
        rows=[dict(probe_key=[1,0,0],original_hz=f,integer_epoch_sample=10,fractional_epoch_offset_samples=epoch,original_margin=.5)
              for f,epoch in ((0.,.1),(2500000/11,.1),(0.,.2),(1000.,.1))]
        self.assertEqual(canonical_rows(rows),[0,2,3])

    def test_pair_denominator_not_candidate_count(self):
        rows=[dict(probe_key=[1,0,0],output_hz=f,original_margin=.5,refinement={}) for f in (0.,5.,2000.)]
        result=pair_histogram(rows,range(3),0.)
        self.assertEqual(result['pairs'],3);self.assertEqual(result['counts'],[1,0,0,0,0,2])
        self.assertEqual(pair_histogram(rows,range(3),.6)['pairs'],0)
