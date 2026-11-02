"""Full-evidence inventory catches predictive omissions and duplicate IDs."""
import unittest
from types import SimpleNamespace
import numpy as np
from combined_evidence_audit import inventory

class EvidenceInventory(unittest.TestCase):
    def fixture(self):
        p=SimpleNamespace(rows=[dict(candidate_norad=11)],members=[0],slices=[slice(0,2)],
            keep=np.array([True,False]),scan=SimpleNamespace(tracks=[dict(observation_ids=['curve','excluded'])]))
        d=dict(entries=[dict(norad=12,observation_ids=['conditional'])],
            families=[SimpleNamespace(entries=[dict(norad=13,observation_ids=['mixture'])])])
        return d,p

    def test_all_three_likelihood_parts_and_mask_are_preserved(self):
        d,p=self.fixture();v=inventory(d,p)
        self.assertEqual(v['ids'],['conditional','curve','mixture'])
        self.assertEqual(v['owners'],{'curve':11,'conditional':12,'mixture':13})
        self.assertEqual(v['counts'],dict(curved=1,conditional_entries=1,phase_mixture_families=1))

    def test_cross_part_native_duplicates_are_rejected(self):
        d,p=self.fixture();d['entries'][0]['observation_ids']=['curve']
        with self.assertRaisesRegex(ValueError,'duplicated'):inventory(d,p)

if __name__=='__main__':unittest.main()
