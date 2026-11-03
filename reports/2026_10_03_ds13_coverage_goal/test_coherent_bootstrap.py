import unittest
import numpy as np
from coherent_bootstrap import local_offset_seeds,wrap,rank_offsets
from benchmark import ALIAS_HZ


class CoherentBootstrapTests(unittest.TestCase):
    def test_no_evidence_produces_no_arbitrary_offset(self):
        self.assertEqual(rank_offsets(np.zeros(10),np.arange(10)),[])

    def test_repeated_peak_copies_do_not_create_ten_probe_support(self):
        edges=np.linspace(-ALIAS_HZ/2,ALIAS_HZ/2,911)
        self.assertEqual(local_offset_seeds(np.zeros(100),np.zeros(100,int),edges),[])

    def test_ten_groups_propose_offset(self):
        edges=np.linspace(-ALIAS_HZ/2,ALIAS_HZ/2,911)
        seeds=local_offset_seeds(np.full(12,17000.),np.arange(12),edges)
        self.assertTrue(any(abs(wrap(seed-17000))<600 for seed in seeds))


if __name__=='__main__':unittest.main()
